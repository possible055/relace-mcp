import atexit
import logging
import os
import subprocess  # nosec B404 - required for LSP server communication
import threading
from pathlib import Path
from typing import Any

from relace_mcp.config.fs_policy import LSP_IGNORED_DIR_NAMES
from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.process_runtime import (
    close_process_streams,
    kill_process_tree,
    resolve_server_command,
    start_server_process,
)
from relace_mcp.lsp.response_parsers import (
    parse_call_hierarchy_item,
    parse_call_info_list,
    parse_document_symbols,
    parse_hover,
    parse_locations,
    parse_symbol_info,
)
from relace_mcp.lsp.transport import JsonRpcTransport
from relace_mcp.lsp.types import (
    CallInfo,
    DocumentSymbol,
    HoverInfo,
    Location,
    LSPError,
    SymbolInfo,
)
from relace_mcp.lsp.workspace_settings import build_workspace_settings
from relace_mcp.lsp.workspace_sync import (
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
            on_server_request=self._handle_server_request,
            read_chunk_size=_READ_CHUNK_SIZE,
        )
        self._initialized = False

        self._workspace_settings = self._build_workspace_settings()

        self._fs_snapshot: dict[str, tuple[int, int]] = {}
        self._fs_snapshot_initialized = False
        self._fs_last_sync = 0.0

        self._atexit_cleanup_handler = self._cleanup
        atexit.register(self._atexit_cleanup_handler)

    def _build_workspace_settings(self) -> dict[str, Any]:
        return build_workspace_settings(
            self._config.workspace_config,
            self._config.language_id,
            self._workspace,
        )

    def _restart_language_server(self, _reason: str) -> None:
        logger.debug("Restarting language server")
        self._fs_snapshot.clear()
        self._fs_snapshot_initialized = False
        self._fs_last_sync = 0.0
        self._workspace_settings = self._build_workspace_settings()
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
            state=WorkspaceSyncState(
                snapshot=self._fs_snapshot,
                snapshot_initialized=self._fs_snapshot_initialized,
                last_sync=self._fs_last_sync,
            ),
            min_interval_seconds=_FS_SYNC_MIN_INTERVAL_SECONDS,
            budget_seconds=_FS_SYNC_BUDGET_SECONDS,
            max_files=_FS_SYNC_MAX_FILES,
            max_events=_FS_SYNC_MAX_EVENTS,
        )
        if outcome is None:
            return

        self._fs_snapshot = outcome.state.snapshot
        self._fs_snapshot_initialized = outcome.state.snapshot_initialized
        self._fs_last_sync = outcome.state.last_sync

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

    def _get_settings_section(self, section: Any) -> Any:
        if not section or not isinstance(section, str):
            return self._workspace_settings

        current: Any = self._workspace_settings
        for part in section.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _handle_server_request(self, req_id: Any, method: Any, params: Any) -> None:
        if not isinstance(method, str):
            try:
                self._send_error_response(req_id, -32601, "Invalid request")
            except Exception:
                return
            return

        try:
            if method in (
                "client/registerCapability",
                "client/unregisterCapability",
                "window/workDoneProgress/create",
            ):
                self._send_response(req_id, None)
                return

            if method == "workspace/workspaceFolders":
                workspace_uri = Path(self._workspace).as_uri()
                self._send_response(
                    req_id, [{"uri": workspace_uri, "name": Path(self._workspace).name}]
                )
                return

            if method == "workspace/configuration":
                items = []
                if isinstance(params, dict):
                    items = params.get("items", [])

                results: list[Any] = []
                if isinstance(items, list):
                    for item in items:
                        section = item.get("section") if isinstance(item, dict) else None
                        results.append(self._get_settings_section(section))

                self._send_response(req_id, results)
                return

            self._send_error_response(req_id, -32601, f"Method not found: {method}")
        except Exception:
            logger.debug("Failed to handle server request")
            try:
                self._send_error_response(req_id, -32603, "Internal error")
            except Exception:
                return

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
                try:
                    self._process = start_server_process(command, self._workspace)
                except FileNotFoundError:
                    executable = command[0] if command else ""
                    install_hint = self._config.install_hint.strip()
                    if install_hint:
                        raise LSPError(
                            f"Language server '{executable}' not found. Install with: {install_hint}"
                        ) from None
                    raise LSPError(f"Language server '{executable}' not found") from None

                self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
                self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
                self._stdout_thread.start()
                self._stderr_thread.start()

            try:
                self._initialize()
            except Exception:
                self._cleanup()
                raise

            with self._lock:
                self._initialized = True

    def _initialize(self) -> None:
        """Send initialize request."""
        workspace_uri = Path(self._workspace).as_uri()

        params: dict[str, Any] = {
            "processId": os.getpid(),
            "rootUri": workspace_uri,
            "rootPath": self._workspace,
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "synchronization": {
                        "didOpen": True,
                        "didClose": True,
                        "didChange": True,
                    },
                },
                "workspace": {
                    # We don't support dynamic workspace folder changes; basedpyright
                    # uses this flag to decide whether it should wait for a
                    # client-side settings update after `initialized`.
                    "workspaceFolders": False,
                    # basedpyright falls back to a server-side file watcher if the
                    # client doesn't support dynamicRegistration for watched files.
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [{"uri": workspace_uri, "name": Path(self._workspace).name}],
        }

        if self._config.initialization_options:
            params["initializationOptions"] = self._config.initialization_options

        self._send_request("initialize", params, timeout=self._startup_timeout)
        self._send_notification("initialized", {})
        # basedpyright resolves workspace initialization after a settings update.
        # Push settings via didChangeConfiguration to unblock language services.
        self._send_notification(
            "workspace/didChangeConfiguration",
            {"settings": self._workspace_settings},
        )

    def _open_file(self, file_path: str) -> str:
        """Open a file and return its URI."""
        # Defense-in-depth: reject absolute paths
        if os.path.isabs(file_path):
            raise LSPError(f"Absolute path not allowed: {file_path}")

        target = Path(self._workspace) / file_path
        # Policy: reject direct symlink paths (defense-in-depth; caller should already validate).
        if target.is_symlink():
            raise LSPError(f"Symlinks not allowed: {file_path}")

        try:
            abs_path = target.resolve()
            workspace_resolved = Path(self._workspace).resolve()
        except (OSError, RuntimeError) as e:
            raise LSPError(f"Invalid path: {e}") from e

        # Validate resolved path is within workspace
        if not abs_path.is_relative_to(workspace_resolved):
            raise LSPError(f"Path escapes workspace: {file_path}")

        uri = abs_path.as_uri()

        try:
            with open(abs_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            raise LSPError(f"Cannot read file: {e}") from e

        self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": self._config.get_language_id(file_path),
                    "version": 1,
                    "text": content,
                }
            },
        )
        return uri

    def _close_file(self, uri: str) -> None:
        """Close a file."""
        self._send_notification("textDocument/didClose", {"textDocument": {"uri": uri}})

    def definition(self, file_path: str, line: int, column: int) -> list[Location]:
        """Get definition locations for a symbol."""
        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._open_file(file_path)
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
                self._close_file(uri)

    def references(
        self, file_path: str, line: int, column: int, include_declaration: bool = True
    ) -> list[Location]:
        """Get all reference locations for a symbol."""
        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._open_file(file_path)
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
                self._close_file(uri)

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
            uri = self._open_file(file_path)
            try:
                result = self._send_request(
                    "textDocument/documentSymbol",
                    {"textDocument": {"uri": uri}},
                )
                return parse_document_symbols(result)
            finally:
                self._close_file(uri)

    def hover(self, file_path: str, line: int, column: int) -> HoverInfo | None:
        """Get type information at position."""

        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            uri = self._open_file(file_path)
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
                self._close_file(uri)

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
            uri = self._open_file(file_path)
            try:
                # Step 1: Prepare call hierarchy
                prepare_result = self._send_request(
                    "textDocument/prepareCallHierarchy",
                    {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": column},
                    },
                )

                if not prepare_result or not isinstance(prepare_result, list):
                    return []

                # Parse the CallHierarchyItem
                raw_item = prepare_result[0]
                item = parse_call_hierarchy_item(raw_item)
                if not item:
                    return []

                # Step 2: Get incoming or outgoing calls
                method = (
                    "callHierarchy/incomingCalls"
                    if direction == "incoming"
                    else "callHierarchy/outgoingCalls"
                )
                calls_result = self._send_request(method, {"item": raw_item})

                return parse_call_info_list(calls_result, direction)
            finally:
                self._close_file(uri)

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
