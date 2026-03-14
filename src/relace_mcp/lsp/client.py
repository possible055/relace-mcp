import atexit
import logging
import subprocess  # nosec B404 - required for LSP server communication
import threading
import time
from typing import Any

from relace_mcp.config.fs_policy import LSP_IGNORED_DIR_NAMES
from relace_mcp.lsp._session import LSPSession
from relace_mcp.lsp.events import (
    log_lsp_server_error,
    log_lsp_server_start,
    log_lsp_server_stop,
)
from relace_mcp.lsp.io.process import (
    close_process_streams,
    kill_process_tree,
    resolve_server_command,
    start_server_process,
)
from relace_mcp.lsp.io.transport import JsonRpcTransport
from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.parsers import (
    parse_call_hierarchy_item,
    parse_call_info_list,
    parse_document_symbols,
    parse_hover,
    parse_locations,
    parse_symbol_info,
)
from relace_mcp.lsp.types import (
    CallInfo,
    DocumentSymbol,
    HoverInfo,
    Location,
    LSPError,
    SymbolInfo,
)
from relace_mcp.lsp.workspace.settings import build_workspace_settings
from relace_mcp.lsp.workspace.sync import (
    WorkspaceSyncState,
    sync_workspace_changes,
)

logger = logging.getLogger(__name__)

# Default timeouts
STARTUP_TIMEOUT = 30.0
REQUEST_TIMEOUT = 10.0
SHUTDOWN_TIMEOUT = 5.0

_READ_CHUNK_SIZE = 8192

_FS_SYNC_MIN_INTERVAL_SECONDS = 5.0
_FS_SYNC_BUDGET_SECONDS = 1.0
_FS_SYNC_MAX_FILES = 20000
_FS_SYNC_MAX_EVENTS = 2000

_DEFAULT_IGNORED_DIR_NAMES = LSP_IGNORED_DIR_NAMES


class LSPClient:
    """LSP client that communicates with a language server via stdio.

    Public methods are synchronous; a background thread reads and dispatches
    JSON-RPC responses.
    """

    def __init__(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._config = config
        self._workspace = workspace
        self._lock = threading.RLock()
        self._request_lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._stop_event = threading.Event()

        if timeout_seconds is None:
            self._startup_timeout = STARTUP_TIMEOUT
            self._request_timeout = REQUEST_TIMEOUT
            self._shutdown_timeout = SHUTDOWN_TIMEOUT
        else:
            self._startup_timeout = timeout_seconds
            self._request_timeout = timeout_seconds
            self._shutdown_timeout = timeout_seconds

        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._transport = JsonRpcTransport(
            lock=self._lock,
            send_lock=self._send_lock,
            stop_event=self._stop_event,
            on_server_request=self._on_server_request,
            read_chunk_size=_READ_CHUNK_SIZE,
        )
        self._initialized = False

        self._workspace_settings = self._build_workspace_settings()
        self._session = self._build_session()

        self._fs_sync_state = WorkspaceSyncState(
            snapshot={},
            snapshot_initialized=False,
            last_sync=0.0,
        )

        self._atexit_cleanup_handler = self._cleanup
        atexit.register(self._atexit_cleanup_handler)

    def _build_workspace_settings(self) -> dict[str, Any]:
        return build_workspace_settings(
            self._config.workspace_config,
            self._config.language_id,
            self._workspace,
        )

    def _build_session(self) -> LSPSession:
        return LSPSession(
            config=self._config,
            workspace=self._workspace,
            workspace_settings=self._workspace_settings,
            send_request_fn=self._send_request,
            send_notification_fn=self._send_notification,
            send_response_fn=self._send_response,
            send_error_response_fn=self._send_error_response,
        )

    def _restart_language_server(self, _reason: str) -> None:
        logger.debug("Restarting language server")
        self._fs_sync_state = WorkspaceSyncState(
            snapshot={},
            snapshot_initialized=False,
            last_sync=0.0,
        )
        self._workspace_settings = self._build_workspace_settings()
        self._session = self._build_session()
        self.shutdown()
        self.start()

    def _sync_workspace_changes(self) -> None:
        if not self._initialized:
            return

        outcome = sync_workspace_changes(
            workspace=self._workspace,
            workspace_settings=self._workspace_settings,
            config_files=self._config.config_files,
            file_extensions=self._config.file_extensions,
            ignored_dir_names=_DEFAULT_IGNORED_DIR_NAMES,
            state=self._fs_sync_state,
            min_interval_seconds=_FS_SYNC_MIN_INTERVAL_SECONDS,
            budget_seconds=_FS_SYNC_BUDGET_SECONDS,
            max_files=_FS_SYNC_MAX_FILES,
            max_events=_FS_SYNC_MAX_EVENTS,
        )
        if outcome is None:
            return

        self._fs_sync_state = outcome.state

        if outcome.restart_reason:
            self._restart_language_server(outcome.restart_reason)
            return

        if outcome.changes:
            self._send_notification("workspace/didChangeWatchedFiles", {"changes": outcome.changes})

    def _sync_workspace_changes_best_effort(self) -> None:
        try:
            self._sync_workspace_changes()
        except Exception as e:
            logger.debug("Workspace file sync failed: %s", e)

    def _cleanup(self) -> None:
        """Cleanup resources (best-effort)."""
        try:
            atexit.unregister(self._atexit_cleanup_handler)
        except Exception:  # nosec B110 - best-effort cleanup
            pass

        with self._lock:
            self._stop_event.set()
            self._initialized = False

            self._transport.cancel_all_pending()

            process = self._process
            self._process = None

        if process:
            try:
                kill_process_tree(process.pid)
            except Exception:  # nosec B110 - best-effort cleanup
                pass

            close_process_streams(process)

        if self._stdout_thread:
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread:
            self._stderr_thread.join(timeout=1.0)

        self._stdout_thread = None
        self._stderr_thread = None
        self._transport.clear_buffer()

    def _read_stdout(self) -> None:
        self._transport.read_stdout_loop(self._process)

    def _drain_stderr(self) -> None:
        """Drain stderr to prevent the server from blocking on a full buffer."""
        self._transport.drain_stderr_loop(self._process)

    def _send_response(self, req_id: Any, result: Any) -> None:
        self._send_message({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _send_error_response(self, req_id: Any, code: int, message: str) -> None:
        self._send_message(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        )

    def _on_server_request(self, req_id: Any, method: Any, params: Any) -> None:
        self._session.handle_server_request(req_id, method, params)

    def _send_message(self, content: dict[str, Any]) -> None:
        """Send a message to the language server."""
        self._transport.send_message(self._process, content)

    def _send_request(
        self, method: str, params: dict[str, Any], *, timeout: float | None = None
    ) -> Any:
        """Send a request and wait for response."""
        effective_timeout = self._request_timeout if timeout is None else timeout
        return self._transport.send_request(
            self._process,
            method,
            params,
            timeout=effective_timeout,
        )

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification (no response expected)."""
        self._transport.send_notification(self._process, method, params)

    def start(self) -> None:
        """Start the language server and initialize it."""
        with self._request_lock:
            with self._lock:
                if self._initialized:
                    return

                command = resolve_server_command(self._config.command, self._config.install_hint)
                self._stop_event.clear()
                started = time.perf_counter()
                try:
                    self._process = start_server_process(command, self._workspace)
                except FileNotFoundError:
                    executable = command[0] if command else ""
                    install_hint = self._config.install_hint.strip()
                    error_msg = (
                        f"Language server '{executable}' not found. Install with: {install_hint}"
                        if install_hint
                        else f"Language server '{executable}' not found"
                    )
                    log_lsp_server_error(
                        self._config.language_id,
                        self._workspace,
                        error_msg,
                        "FileNotFoundError",
                    )
                    raise LSPError(error_msg) from None

                self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
                self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
                self._stdout_thread.start()
                self._stderr_thread.start()

            try:
                self._session.initialize(self._startup_timeout)
            except Exception as exc:
                log_lsp_server_error(
                    self._config.language_id,
                    self._workspace,
                    str(exc),
                    type(exc).__name__,
                )
                self._cleanup()
                raise

            latency_ms = (time.perf_counter() - started) * 1000
            with self._lock:
                self._initialized = True
            log_lsp_server_start(
                self._config.language_id,
                self._workspace,
                command,
                latency_ms,
            )

    def definition(self, file_path: str, line: int, column: int) -> list[Location]:
        """Get definition locations for a symbol."""
        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._session.open_file(file_path)
            try:
                result = self._send_request(
                    "textDocument/definition",
                    {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": column},
                    },
                )
                return parse_locations(result)
            finally:
                self._session.close_file(uri)

    def references(
        self, file_path: str, line: int, column: int, include_declaration: bool = True
    ) -> list[Location]:
        """Get all reference locations for a symbol."""
        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._session.open_file(file_path)
            try:
                result = self._send_request(
                    "textDocument/references",
                    {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": column},
                        "context": {"includeDeclaration": include_declaration},
                    },
                )
                return parse_locations(result)
            finally:
                self._session.close_file(uri)

    def workspace_symbols(self, query: str) -> list[SymbolInfo]:
        """Search for symbols by name across the workspace."""

        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            result = self._send_request("workspace/symbol", {"query": query})
            return parse_symbol_info(result)

    def document_symbols(self, file_path: str) -> list[DocumentSymbol]:
        """Get all symbols defined in a file."""

        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._session.open_file(file_path)
            try:
                result = self._send_request(
                    "textDocument/documentSymbol",
                    {"textDocument": {"uri": uri}},
                )
                return parse_document_symbols(result)
            finally:
                self._session.close_file(uri)

    def hover(self, file_path: str, line: int, column: int) -> HoverInfo | None:
        """Get type information at position."""

        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._session.open_file(file_path)
            try:
                result = self._send_request(
                    "textDocument/hover",
                    {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": column},
                    },
                )
                return parse_hover(result)
            finally:
                self._session.close_file(uri)

    def call_hierarchy(
        self, file_path: str, line: int, column: int, direction: str = "incoming"
    ) -> list[CallInfo]:
        """Get call hierarchy for a symbol.

        Args:
            file_path: Relative path to the file.
            line: 0-indexed line number.
            column: 0-indexed column number.
            direction: "incoming" (who calls this) or "outgoing" (what this calls).

        Returns:
            List of CallInfo representing callers or callees.
        """

        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._session.open_file(file_path)
            try:
                prepare_result = self._send_request(
                    "textDocument/prepareCallHierarchy",
                    {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": column},
                    },
                )

                if not prepare_result or not isinstance(prepare_result, list):
                    return []

                raw_item = prepare_result[0]
                item = parse_call_hierarchy_item(raw_item)
                if not item:
                    return []

                method = (
                    "callHierarchy/incomingCalls"
                    if direction == "incoming"
                    else "callHierarchy/outgoingCalls"
                )
                calls_result = self._send_request(method, {"item": raw_item})

                return parse_call_info_list(calls_result, direction)
            finally:
                self._session.close_file(uri)

    def shutdown(self) -> None:
        """Shutdown the language server gracefully."""
        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    self._cleanup()
                    return

            try:
                self._send_request("shutdown", {}, timeout=self._shutdown_timeout)
                self._send_notification("exit", {})
            except Exception as e:
                logger.debug("Shutdown error: %s", e)
            finally:
                self._cleanup()
                log_lsp_server_stop(self._config.language_id, self._workspace)
