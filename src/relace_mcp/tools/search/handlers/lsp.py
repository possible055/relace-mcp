import atexit
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import MAX_LSP_RESULTS
from .paths import map_repo_path

logger = logging.getLogger(__name__)


class LSPServerManager:
    """Process-scoped singleton manager for LSP server.

    Thread-safe: Uses RLock to protect all operations.
    Lifecycle: Server starts on first request, stops on process exit.
    """

    _instance: "LSPServerManager | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._server: Any = None  # SyncLanguageServer
        self._context: Any = None  # Context manager state
        self._workspace: str | None = None
        self._initialized = False

        # Register cleanup on process exit
        atexit.register(self._cleanup)

    @classmethod
    def get_instance(cls) -> "LSPServerManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _cleanup(self) -> None:
        """Cleanup resources on process exit."""
        with self._lock:
            context = self._context

            # Always clear state, even if context is missing (defense-in-depth)
            self._server = None
            self._context = None
            self._initialized = False

            if context is None:
                return

            try:
                logger.debug("Shutting down LSP server...")
                context.__exit__(None, None, None)
            except Exception as exc:
                logger.warning("Error during LSP cleanup: %s", exc)

    def _ensure_server(self, workspace: str) -> None:
        """Ensure server is running for the given workspace.

        If workspace changed, restart server.
        Must be called with lock held.
        """
        # Lazy import to avoid loading multilspy if not used
        from multilspy import SyncLanguageServer
        from multilspy.multilspy_config import MultilspyConfig
        from multilspy.multilspy_logger import MultilspyLogger

        # Check if we need to restart (workspace changed)
        if self._initialized and self._workspace != workspace:
            logger.info("Workspace changed, restarting LSP server...")
            self._cleanup()

        if not self._initialized:
            logger.info("Starting LSP server for workspace: %s", workspace)
            config = MultilspyConfig.from_dict({"code_language": "python"})
            lsp_logger = MultilspyLogger()
            lsp_logger.logger.setLevel(logging.WARNING)

            server = None
            context = None
            try:
                server = SyncLanguageServer.create(config, lsp_logger, workspace)
                context = server.start_server()
                context.__enter__()
                self._server = server
                self._context = context
                self._workspace = workspace
                self._initialized = True
                logger.info("LSP server started successfully")
            except Exception:
                try:
                    if context is not None:
                        context.__exit__(None, None, None)
                except Exception as exc:
                    logger.warning("Error during LSP startup cleanup: %s", exc)
                finally:
                    self._initialized = False
                    self._server = None
                    self._context = None
                raise

    def request_definition(
        self, workspace: str, rel_path: str, line: int, col: int
    ) -> list[dict[str, Any]]:
        """Thread-safe definition request."""
        with self._lock:
            try:
                self._ensure_server(workspace)
                result: list[dict[str, Any]] = self._server.request_definition(rel_path, line, col)
                return result
            except Exception:
                # Server might be in bad state, force cleanup and restart on next call
                self._cleanup()
                raise

    def request_references(
        self, workspace: str, rel_path: str, line: int, col: int
    ) -> list[dict[str, Any]]:
        """Thread-safe references request."""
        with self._lock:
            try:
                self._ensure_server(workspace)
                result: list[dict[str, Any]] = self._server.request_references(rel_path, line, col)
                return result
            except Exception:
                # Server might be in bad state, force cleanup and restart on next call
                self._cleanup()
                raise


@dataclass
class LSPQueryParams:
    """Parameters for lsp_query tool."""

    action: str  # "definition" | "references"
    file: str
    line: int
    column: int


def lsp_query_handler(params: LSPQueryParams, base_dir: str) -> str:
    """LSP query handler with process-scoped server persistence.

    Thread-safe through LSPServerManager's internal locking.
    First call incurs 2-5s startup delay, subsequent calls are fast.
    """
    # Validate action first (no need for imports)
    if params.action not in ("definition", "references"):
        return f"Error: Unknown action '{params.action}'. Use 'definition' or 'references'."

    if not isinstance(params.line, int) or not isinstance(params.column, int):
        return "Error: line and column must be integers (0-indexed)."

    if params.line < 0:
        return "Error: line must be >= 0 (0-indexed)."

    if params.column < 0:
        return "Error: column must be >= 0 (0-indexed)."

    # Check multilspy availability
    try:
        import multilspy  # noqa: F401
    except ImportError:
        return "Error: multilspy not installed. Run: pip install multilspy"

    # Path validation and mapping
    try:
        fs_path = map_repo_path(params.file, base_dir)
        abs_path = Path(fs_path).resolve()

        if not abs_path.exists():
            return f"Error: File not found: {params.file}"
        if abs_path.suffix != ".py":
            return f"Error: LSP query only supports Python files, got: {abs_path.suffix}"

        rel_path = str(abs_path.relative_to(base_dir))
    except ValueError as e:
        return f"Error: Invalid path: {e}"

    # Execute LSP request through manager
    try:
        manager = LSPServerManager.get_instance()

        if params.action == "definition":
            results = manager.request_definition(base_dir, rel_path, params.line, params.column)
        else:
            results = manager.request_references(base_dir, rel_path, params.line, params.column)

        return _format_lsp_results(results, base_dir)

    except FileNotFoundError:
        return "Error: jedi-language-server not found. Run: pip install jedi-language-server"
    except Exception as exc:
        logger.warning("LSP query failed: %s", exc)
        return f"Error: LSP query failed: {exc}"


def _format_lsp_results(results: list[dict[str, Any]], base_dir: str) -> str:
    """Format LSP results into grep-like output."""
    if not results:
        return "No results found."

    lines = []
    for r in results[:MAX_LSP_RESULTS]:
        uri = r.get("uri") or r.get("targetUri", "")
        rng = r.get("range") or r.get("targetRange", {})
        start = rng.get("start", {})

        path = uri.replace("file://", "")
        if path.startswith(base_dir):
            path = "/repo" + path[len(base_dir) :]

        line_num = start.get("line", 0) + 1
        col_num = start.get("character", 0)
        lines.append(f"{path}:{line_num}:{col_num}")

    if len(results) > MAX_LSP_RESULTS:
        lines.append(f"... capped at {MAX_LSP_RESULTS} results (total: {len(results)})")

    return "\n".join(lines)
