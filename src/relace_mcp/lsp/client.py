import atexit
import concurrent.futures
import logging
import os
import shutil
import subprocess  # nosec B404 - required for LSP server communication
import sys
import threading
from pathlib import Path
from typing import Any

from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.protocol import MessageBuffer, encode_message
from relace_mcp.lsp.types import Location, LSPError

logger = logging.getLogger(__name__)

# Default timeouts
STARTUP_TIMEOUT = 30.0
REQUEST_TIMEOUT = 10.0
SHUTDOWN_TIMEOUT = 5.0

_READ_CHUNK_SIZE = 8192


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
        self._message_buffer = MessageBuffer()

        self._request_id = 0
        self._pending_requests: dict[int, concurrent.futures.Future[Any]] = {}
        self._initialized = False

        atexit.register(self._cleanup)

    def _resolve_command(self, command: list[str]) -> list[str]:
        """Resolve the language server executable path.

        If the environment running relace-mcp hasn't activated its virtualenv,
        the venv's scripts directory may not be on PATH. In that case, look for
        the executable next to the current Python interpreter.
        """
        if not command:
            raise LSPError("Language server command is empty")

        executable = command[0]
        if not executable:
            raise LSPError("Language server executable is empty")

        # If already a path (absolute or contains a separator), validate it.
        if any(sep in executable for sep in (os.sep, "/", "\\")):
            path = Path(executable)
            if path.exists():
                return [str(path), *command[1:]]
            raise LSPError(f"Language server not found: {executable}")

        resolved = shutil.which(executable)
        if resolved:
            return [resolved, *command[1:]]

        scripts_dirs: list[Path] = []
        try:
            scripts_dirs.append(Path(sys.executable).parent)
        except Exception:  # nosec B110 - best-effort path resolution
            pass
        try:
            scripts_dirs.append(Path(sys.executable).resolve().parent)
        except Exception:  # nosec B110 - best-effort path resolution
            pass
        try:
            import sysconfig

            scripts_dirs.append(Path(sysconfig.get_path("scripts")))
        except Exception:  # nosec B110 - best-effort path resolution
            pass

        seen: set[Path] = set()
        for d in scripts_dirs:
            if d and d not in seen:
                seen.add(d)
        candidates = list(seen)
        for scripts_dir in candidates:
            candidate = scripts_dir / executable
            if candidate.exists():
                return [str(candidate), *command[1:]]

        raise LSPError(
            f"Language server not found: {executable}. Ensure it is installed and on PATH "
            f"(or located in one of: {', '.join(str(p) for p in candidates)})."
        )

    def _kill_process_tree(self, pid: int) -> None:
        """Kill process and all children."""
        try:
            import psutil
        except ImportError:
            # Fallback: just kill the main process
            if self._process:
                self._process.kill()
            return

        try:
            parent = psutil.Process(pid)
        except psutil.Error:
            return

        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.Error:
                pass
        try:
            parent.kill()
        except psutil.Error:
            pass

    def _cleanup(self) -> None:
        """Cleanup resources (best-effort)."""
        with self._lock:
            self._stop_event.set()
            self._initialized = False

            pending = list(self._pending_requests.values())
            self._pending_requests.clear()
            for fut in pending:
                if not fut.done():
                    fut.cancel()

            process = self._process
            self._process = None

        if process:
            try:
                self._kill_process_tree(process.pid)
            except Exception:  # nosec B110 - best-effort cleanup
                pass

            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:  # nosec B110 - best-effort cleanup
                    pass

        if self._stdout_thread:
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread:
            self._stderr_thread.join(timeout=1.0)

        self._stdout_thread = None
        self._stderr_thread = None
        self._message_buffer.clear()

    def _fail_all_pending(self, error: Exception) -> None:
        with self._lock:
            pending = list(self._pending_requests.values())
            self._pending_requests.clear()

        for fut in pending:
            if fut.done():
                continue
            fut.set_exception(error)

    def _read_stdout(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return

        try:
            fd = process.stdout.fileno()
            while not self._stop_event.is_set():
                data = os.read(fd, _READ_CHUNK_SIZE)
                if not data:
                    break

                self._message_buffer.append(data)
                while True:
                    msg = self._message_buffer.try_parse_message()
                    if msg is None:
                        break
                    self._handle_message(msg)
        except Exception as e:
            logger.debug("LSP stdout reader stopped: %s", e)
        finally:
            if not self._stop_event.is_set():
                self._fail_all_pending(LSPError("Language server exited"))

    def _drain_stderr(self) -> None:
        """Drain stderr to prevent the server from blocking on a full buffer."""
        process = self._process
        if not process or not process.stderr:
            return

        try:
            for line in iter(process.stderr.readline, b""):
                if not line:
                    break
                logger.debug("LSP stderr: %s", line.decode("utf-8", errors="replace").rstrip())
        except Exception:
            return

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle an incoming message from the language server."""
        if "id" in msg and "method" not in msg:
            req_id = msg["id"]
            with self._lock:
                future = self._pending_requests.pop(req_id, None)
            if future is None:
                return

            if "error" in msg:
                error = msg["error"]
                future.set_exception(
                    LSPError(error.get("message", "Unknown error"), error.get("code"))
                )
            else:
                future.set_result(msg.get("result"))
            return

        if "method" in msg:
            method = msg["method"]
            if method == "window/logMessage":
                params = msg.get("params", {})
                logger.debug("LSP: %s", params.get("message", ""))

    def _send_message(self, content: dict[str, Any]) -> None:
        """Send a message to the language server."""
        process = self._process
        if not process or not process.stdin:
            raise LSPError("Language server not running")

        data = encode_message(content)
        try:
            process.stdin.write(data)
            process.stdin.flush()
        except BrokenPipeError as e:
            raise LSPError(f"Language server stdin closed: {e}") from e

    def _send_request(
        self, method: str, params: dict[str, Any], *, timeout: float | None = None
    ) -> Any:
        """Send a request and wait for response."""
        effective_timeout = self._request_timeout if timeout is None else timeout

        with self._lock:
            if not self._process:
                raise LSPError("Language server not running")
            self._request_id += 1
            req_id = self._request_id
            future: concurrent.futures.Future[Any] = concurrent.futures.Future()
            self._pending_requests[req_id] = future

        try:
            self._send_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params,
                }
            )
        except Exception:
            # Clean up pending request on send failure to prevent resource leak
            with self._lock:
                self._pending_requests.pop(req_id, None)
            raise

        try:
            return future.result(timeout=effective_timeout)
        except TimeoutError:
            with self._lock:
                self._pending_requests.pop(req_id, None)
            raise LSPError(f"Request {method} timed out") from None

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification (no response expected)."""
        self._send_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )

    def start(self) -> None:
        """Start the language server and initialize it."""
        with self._request_lock:
            with self._lock:
                if self._initialized:
                    return

                command = self._resolve_command(self._config.command)
                logger.info("Starting language server: %s", " ".join(command))

                self._stop_event.clear()
                try:
                    self._process = subprocess.Popen(  # nosec B603 - trusted command
                        command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=self._workspace,
                    )
                except FileNotFoundError:
                    raise LSPError(f"Language server not found: {command[0]}") from None

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
                },
            },
            "workspaceFolders": [{"uri": workspace_uri, "name": Path(self._workspace).name}],
        }

        if self._config.initialization_options:
            params["initializationOptions"] = self._config.initialization_options

        self._send_request("initialize", params, timeout=self._startup_timeout)
        self._send_notification("initialized", {})
        # basedpyright resolves workspace initialization after a settings update.
        # We don't support workspace/configuration requests, so push settings via
        # didChangeConfiguration to unblock language services.
        self._send_notification(
            "workspace/didChangeConfiguration",
            {"settings": self._config.workspace_config},
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
                    "languageId": self._config.language_id,
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

            uri = self._open_file(file_path)
            try:
                result = self._send_request(
                    "textDocument/definition",
                    {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": column},
                    },
                )
                return self._parse_locations(result)
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
                return self._parse_locations(result)
            finally:
                self._close_file(uri)

    def _parse_locations(self, result: Any) -> list[Location]:
        """Parse LSP locations from response."""
        if result is None:
            return []

        # Handle single Location
        if isinstance(result, dict) and "uri" in result:
            result = [result]

        if not isinstance(result, list):
            return []

        locations: list[Location] = []
        for item in result:
            if not isinstance(item, dict):
                continue

            uri = item.get("uri") or item.get("targetUri", "")
            rng = item.get("range") or item.get("targetRange", {})
            start = rng.get("start", {})

            if uri:
                locations.append(
                    Location(
                        uri=uri,
                        line=start.get("line", 0),
                        character=start.get("character", 0),
                    )
                )

        return locations

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


class LSPClientManager:
    """Process-scoped singleton manager for LSP clients.

    Thread-safe: Uses RLock to protect all operations.
    """

    _instance: "LSPClientManager | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._clients: dict[str, LSPClient] = {}  # workspace -> client
        atexit.register(self._cleanup_all)

    @classmethod
    def get_instance(cls) -> "LSPClientManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _cleanup_all(self) -> None:
        """Cleanup all clients."""
        with self._lock:
            for client in list(self._clients.values()):
                try:
                    client.shutdown()
                except Exception:  # nosec B110 - best-effort cleanup
                    pass
            self._clients.clear()

    def get_client(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None = None,
    ) -> LSPClient:
        """Get or create a client for the given workspace."""
        with self._lock:
            if workspace not in self._clients:
                client = LSPClient(config, workspace, timeout_seconds=timeout_seconds)
                client.start()
                self._clients[workspace] = client
            return self._clients[workspace]
