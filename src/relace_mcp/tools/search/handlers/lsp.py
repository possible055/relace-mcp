import asyncio
import atexit
import logging
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .constants import LSP_LOOP_STOP_TIMEOUT_SECONDS, LSP_TIMEOUT_SECONDS, MAX_LSP_RESULTS
from .paths import map_repo_path

logger = logging.getLogger(__name__)


def _run_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


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
        self._context: Any = None  # Async context manager state (LanguageServer.start_server)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
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
            server = self._server
            context = self._context
            loop = self._loop
            loop_thread = self._loop_thread

            # Always clear state (defense-in-depth)
            self._server = None
            self._context = None
            self._loop = None
            self._loop_thread = None
            self._workspace = None
            self._initialized = False

            if server is None or context is None or loop is None or loop_thread is None:
                return

            try:
                logger.debug("Shutting down LSP server...")
                fut = asyncio.run_coroutine_threadsafe(context.__aexit__(None, None, None), loop)
                fut.result(timeout=LSP_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                try:
                    fut.cancel()
                except Exception:  # nosec B110 - cleanup best-effort
                    pass
                logger.warning(
                    "LSP cleanup timed out after %.1fs; forcing stop", LSP_TIMEOUT_SECONDS
                )
                self._force_stop(server, loop)
            except Exception:
                logger.warning("Error during LSP cleanup", exc_info=True)
            finally:
                self._stop_loop(loop, loop_thread)

    def _stop_loop(self, loop: asyncio.AbstractEventLoop, loop_thread: threading.Thread) -> None:
        try:
            loop.call_soon_threadsafe(loop.stop)
        except Exception:  # nosec B110 - cleanup best-effort
            pass

        loop_thread.join(timeout=LSP_LOOP_STOP_TIMEOUT_SECONDS)
        if loop_thread.is_alive():
            return

        try:
            loop.close()
        except Exception:  # nosec B110 - cleanup best-effort
            pass

    def _kill_process_tree(self, pid: int) -> None:
        try:
            import psutil
        except Exception:
            return

        try:
            parent = psutil.Process(pid)
        except Exception:
            return

        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:  # nosec B110 - cleanup best-effort
                pass
        try:
            parent.kill()
        except Exception:  # nosec B110 - cleanup best-effort
            pass

    def _force_stop(self, server: Any, loop: asyncio.AbstractEventLoop) -> None:
        """Forcefully stop the language server process (best-effort)."""
        try:
            fut = asyncio.run_coroutine_threadsafe(server.language_server.server.stop(), loop)
            fut.result(timeout=LSP_TIMEOUT_SECONDS)
            return
        except Exception:  # nosec B110 - cleanup best-effort, fallback below
            pass

        try:
            process = server.language_server.server.process
            pid = getattr(process, "pid", None)
        except Exception:
            process = None
            pid = None

        if isinstance(pid, int) and pid > 0:
            self._kill_process_tree(pid)
            return

        try:
            if process is not None:
                process.kill()
        except Exception:  # nosec B110 - cleanup best-effort
            pass

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

            server: Any | None = None
            loop: asyncio.AbstractEventLoop | None = None
            loop_thread: threading.Thread | None = None
            context: Any | None = None
            fut: Any | None = None

            try:
                server = SyncLanguageServer.create(
                    config, lsp_logger, workspace, timeout=max(1, int(LSP_TIMEOUT_SECONDS))
                )

                loop = asyncio.new_event_loop()
                loop_thread = threading.Thread(
                    target=_run_event_loop,
                    args=(loop,),
                    daemon=True,
                )
                loop_thread.start()
                cast(Any, server).loop = loop

                context = server.language_server.start_server()
                fut = asyncio.run_coroutine_threadsafe(context.__aenter__(), loop)
                fut.result(timeout=LSP_TIMEOUT_SECONDS)

                self._server = server
                self._context = context
                self._loop = loop
                self._loop_thread = loop_thread
                self._workspace = workspace
                self._initialized = True
                logger.info("LSP server started successfully")
            except FuturesTimeoutError as exc:
                if fut is not None:
                    try:
                        fut.cancel()
                    except Exception:  # nosec B110 - cleanup best-effort
                        pass
                logger.warning(
                    "LSP startup timed out after %.1fs", LSP_TIMEOUT_SECONDS, exc_info=True
                )
                try:
                    if server is not None and loop is not None:
                        self._force_stop(server, loop)
                finally:
                    if loop is not None and loop_thread is not None:
                        self._stop_loop(loop, loop_thread)
                raise TimeoutError(
                    f"LSP startup timed out after {LSP_TIMEOUT_SECONDS:.1f} seconds"
                ) from exc
            except Exception:
                if context is not None and loop is not None:
                    try:
                        exit_fut = asyncio.run_coroutine_threadsafe(
                            context.__aexit__(None, None, None), loop
                        )
                        exit_fut.result(timeout=LSP_TIMEOUT_SECONDS)
                    except Exception as exc:
                        logger.warning("Error during LSP startup cleanup: %s", exc)
                        if server is not None:
                            self._force_stop(server, loop)
                elif server is not None and loop is not None:
                    self._force_stop(server, loop)

                if loop is not None and loop_thread is not None:
                    self._stop_loop(loop, loop_thread)
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
        resolved_base_dir = str(Path(base_dir).resolve())

        if not abs_path.exists():
            return f"Error: File not found: {params.file}"
        if abs_path.suffix != ".py":
            return f"Error: LSP query only supports Python files, got: {abs_path.suffix}"

        rel_path = str(abs_path.relative_to(resolved_base_dir))
    except ValueError as e:
        return f"Error: Invalid path: {e}"

    # Execute LSP request through manager
    try:
        manager = LSPServerManager.get_instance()

        if params.action == "definition":
            results = manager.request_definition(
                resolved_base_dir, rel_path, params.line, params.column
            )
        else:
            results = manager.request_references(
                resolved_base_dir, rel_path, params.line, params.column
            )

        return _format_lsp_results(results, resolved_base_dir)

    except FileNotFoundError:
        return "Error: jedi-language-server not found. Run: pip install jedi-language-server"
    except (FuturesTimeoutError, TimeoutError):
        return f"Error: LSP query timed out after {LSP_TIMEOUT_SECONDS:.1f} seconds."
    except Exception as exc:
        logger.warning("LSP query failed: %s", exc)
        return f"Error: LSP query failed: {exc}"


def _format_lsp_results(results: list[dict[str, Any]], base_dir: str) -> str:
    """Format LSP results into grep-like output."""
    if not results:
        return "No results found."

    lines = []
    # Ensure base_dir ends with / to match directory boundary correctly
    # e.g., avoid matching /home/user/project123 when base_dir is /home/user/project
    base_dir_prefix = base_dir if base_dir.endswith("/") else base_dir + "/"
    for r in results[:MAX_LSP_RESULTS]:
        uri = r.get("uri") or r.get("targetUri", "")
        rng = r.get("range") or r.get("targetRange", {})
        start = rng.get("start", {})

        path = uri.replace("file://", "")
        if path.startswith(base_dir_prefix):
            path = "/repo/" + path[len(base_dir_prefix) :]

        line_num = start.get("line", 0) + 1
        col_num = start.get("character", 0)
        lines.append(f"{path}:{line_num}:{col_num}")

    if len(results) > MAX_LSP_RESULTS:
        lines.append(f"... capped at {MAX_LSP_RESULTS} results (total: {len(results)})")

    return "\n".join(lines)
