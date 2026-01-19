import atexit
import concurrent.futures
import copy
import fnmatch
import json
import logging
import os
import shutil
import signal
import subprocess  # nosec B404 - required for LSP server communication
import sys
import threading
import time
import tomllib
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from relace_mcp.config.compat import getenv_with_fallback
from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.protocol import MessageBuffer, encode_message
from relace_mcp.lsp.types import (
    CallHierarchyItem,
    CallInfo,
    DocumentSymbol,
    HoverInfo,
    Location,
    LSPError,
    SymbolInfo,
)

if TYPE_CHECKING:
    pass

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

_CONFIG_FILE_NAMES = ("pyrightconfig.json", "pyproject.toml")

_DEFAULT_IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".direnv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "target",
        "venv",
    }
)


def _deep_update_dict(target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update_dict(target[key], value)
        else:
            target[key] = value
    return target


def _parse_nonnegative_int_env_with_fallback(new_name: str, old_name: str, default: int) -> int:
    raw = getenv_with_fallback(new_name, old_name).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 0:
        return default
    return value


def _normalize_str_list(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None

    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if stripped:
            values.append(stripped)
    return values


def _read_pyrightconfig(workspace: Path) -> dict[str, Any]:
    path = workspace / "pyrightconfig.json"
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Failed to read pyrightconfig.json: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    analysis: dict[str, Any] = {}
    for key in ("include", "exclude", "ignore"):
        values = _normalize_str_list(data.get(key))
        if values is not None:
            analysis[key] = values

    if not analysis:
        return {}
    return {"basedpyright": {"analysis": analysis}}


def _read_pyproject(workspace: Path) -> dict[str, Any]:
    path = workspace / "pyproject.toml"
    if not path.is_file():
        return {}

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Failed to read pyproject.toml: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}

    section = tool.get("basedpyright")
    if not isinstance(section, dict):
        section = tool.get("pyright")
    if not isinstance(section, dict):
        return {}

    analysis: dict[str, Any] = {}
    for key in ("include", "exclude", "ignore"):
        values = _normalize_str_list(section.get(key))
        if values is not None:
            analysis[key] = values

    if not analysis:
        return {}
    return {"basedpyright": {"analysis": analysis}}


def _load_project_workspace_settings(workspace: Path) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    _deep_update_dict(settings, _read_pyproject(workspace))
    _deep_update_dict(settings, _read_pyrightconfig(workspace))
    return settings


def _normalize_glob_pattern(raw: str) -> str:
    pattern = raw.strip().replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.lstrip("/")
    return pattern


def _expand_glob_patterns(raw_patterns: list[str]) -> list[str]:
    patterns: list[str] = []
    seen: set[str] = set()
    for raw in raw_patterns:
        base = _normalize_glob_pattern(raw)
        if not base:
            continue

        candidate = base
        while True:
            if candidate and candidate not in seen:
                seen.add(candidate)
                patterns.append(candidate)

            if "/**/" in candidate:
                candidate = candidate.replace("/**/", "/", 1)
                continue

            if candidate.endswith("/**"):
                candidate = candidate[:-3]
                continue

            break
    return patterns


def _iter_parent_paths(rel_path: str) -> list[str]:
    parents: list[str] = []
    parts = rel_path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        parents.append("/".join(parts[:i]))
    return parents


def _matches_any_pattern(rel_path: str, patterns: list[str]) -> bool:
    if not patterns:
        return False

    if any(fnmatch.fnmatchcase(rel_path, pattern) for pattern in patterns):
        return True

    parents = _iter_parent_paths(rel_path)
    for parent in parents:
        if any(fnmatch.fnmatchcase(parent, pattern) for pattern in patterns):
            return True

    return False


def _extract_glob_prefix(raw: str) -> str:
    pattern = _normalize_glob_pattern(raw)
    if not pattern:
        return ""

    parts = [p for p in pattern.split("/") if p and p != "."]
    prefix_parts: list[str] = []
    for part in parts:
        if any(ch in part for ch in ("*", "?", "[")):
            break
        prefix_parts.append(part)

    return "/".join(prefix_parts)


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
        self._message_buffer = MessageBuffer()

        self._request_id = 0
        self._pending_requests: dict[int, concurrent.futures.Future[Any]] = {}
        self._initialized = False

        self._workspace_settings = self._build_workspace_settings()

        self._fs_snapshot: dict[str, tuple[int, int]] = {}
        self._fs_snapshot_initialized = False
        self._fs_last_sync = 0.0

        self._atexit_cleanup_handler = self._cleanup
        atexit.register(self._atexit_cleanup_handler)

    def _build_workspace_settings(self) -> dict[str, Any]:
        settings = copy.deepcopy(self._config.workspace_config)
        project_settings = _load_project_workspace_settings(Path(self._workspace))
        _deep_update_dict(settings, project_settings)
        return settings

    def _get_analysis_patterns(self) -> tuple[list[str], list[str], list[str]]:
        basedpyright = self._workspace_settings.get("basedpyright")
        if not isinstance(basedpyright, dict):
            return ([], [], [])

        analysis = basedpyright.get("analysis")
        if not isinstance(analysis, dict):
            return ([], [], [])

        include = analysis.get("include")
        exclude = analysis.get("exclude")
        ignore = analysis.get("ignore")

        include_patterns = include if isinstance(include, list) else []
        exclude_patterns = exclude if isinstance(exclude, list) else []
        ignore_patterns = ignore if isinstance(ignore, list) else []
        return (
            [p for p in include_patterns if isinstance(p, str)],
            [p for p in exclude_patterns if isinstance(p, str)],
            [p for p in ignore_patterns if isinstance(p, str)],
        )

    def _restart_language_server(self, reason: str) -> None:
        logger.info("Restarting language server")
        self._fs_snapshot.clear()
        self._fs_snapshot_initialized = False
        self._fs_last_sync = 0.0
        self._workspace_settings = self._build_workspace_settings()
        self.shutdown()
        self.start()

    def _sync_workspace_changes(self) -> None:
        if not self._initialized:
            return

        now = time.monotonic()
        if now - self._fs_last_sync < _FS_SYNC_MIN_INTERVAL_SECONDS:
            return
        self._fs_last_sync = now

        workspace_root = Path(self._workspace)
        include_raw, exclude_raw, _ = self._get_analysis_patterns()
        include_patterns = _expand_glob_patterns(include_raw)
        exclude_patterns = _expand_glob_patterns(exclude_raw)

        scan_roots: list[Path] = []
        if include_raw:
            root_candidates: set[Path] = set()
            for raw in include_raw:
                prefix = _extract_glob_prefix(raw)
                if not prefix:
                    continue
                candidate = workspace_root / prefix
                if candidate.is_dir():
                    root_candidates.add(candidate)
                elif candidate.is_file() and candidate.parent.is_dir():
                    root_candidates.add(candidate.parent)
            scan_roots = sorted(root_candidates) if root_candidates else [workspace_root]
        else:
            scan_roots = [workspace_root]

        start = time.monotonic()
        scanned_files = 0
        truncated = False

        def should_consider(rel_path: str) -> bool:
            if include_patterns and not _matches_any_pattern(rel_path, include_patterns):
                return False
            if _matches_any_pattern(rel_path, exclude_patterns):
                return False
            return True

        def should_skip_dir(rel_dir: str, dir_name: str) -> bool:
            if rel_dir not in ("", ".") and dir_name in _DEFAULT_IGNORED_DIR_NAMES:
                return True
            if _matches_any_pattern(rel_dir, exclude_patterns):
                return True
            return False

        current_snapshot: dict[str, tuple[int, int]] = {}

        def record_path(path: Path) -> None:
            nonlocal scanned_files, truncated
            if path.is_symlink():
                return
            try:
                rel_path = path.relative_to(workspace_root).as_posix()
            except ValueError:
                return
            try:
                st = path.stat()
            except OSError:
                return
            if rel_path not in _CONFIG_FILE_NAMES and not should_consider(rel_path):
                return
            current_snapshot[rel_path] = (st.st_mtime_ns, st.st_size)
            scanned_files += 1
            if scanned_files >= _FS_SYNC_MAX_FILES:
                truncated = True

        for cfg in _CONFIG_FILE_NAMES:
            record_path(workspace_root / cfg)

        pending_dirs: list[Path] = list(reversed(scan_roots))
        while pending_dirs and not truncated:
            if time.monotonic() - start > _FS_SYNC_BUDGET_SECONDS:
                truncated = True
                break

            current_dir = pending_dirs.pop()
            try:
                rel_dir = current_dir.relative_to(workspace_root).as_posix()
            except ValueError:
                continue

            if rel_dir and should_skip_dir(rel_dir, current_dir.name):
                continue

            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if time.monotonic() - start > _FS_SYNC_BUDGET_SECONDS:
                            truncated = True
                            break
                        if scanned_files >= _FS_SYNC_MAX_FILES:
                            truncated = True
                            break
                        if entry.is_symlink():
                            continue

                        try:
                            if entry.is_dir(follow_symlinks=False):
                                child_dir = Path(entry.path)
                                try:
                                    child_rel = child_dir.relative_to(workspace_root).as_posix()
                                except ValueError:
                                    continue
                                if should_skip_dir(child_rel, entry.name):
                                    continue
                                pending_dirs.append(child_dir)
                                continue

                            if not entry.is_file(follow_symlinks=False):
                                continue
                        except OSError:
                            continue

                        name = entry.name
                        if not (name.endswith(".py") or name.endswith(".pyi")):
                            continue

                        record_path(Path(entry.path))
            except OSError:
                continue

        if not self._fs_snapshot_initialized:
            self._fs_snapshot = current_snapshot
            self._fs_snapshot_initialized = True
            return

        changes: list[tuple[int, str]] = []
        config_changed = False

        for rel_path, meta in current_snapshot.items():
            prev = self._fs_snapshot.get(rel_path)
            if prev is None:
                changes.append((1, rel_path))
            elif prev != meta:
                changes.append((2, rel_path))
            if rel_path in _CONFIG_FILE_NAMES:
                config_changed = config_changed or prev != meta

        if truncated:
            for cfg in _CONFIG_FILE_NAMES:
                if cfg in self._fs_snapshot and cfg not in current_snapshot:
                    changes.append((3, cfg))
                    config_changed = True

        if not truncated:
            for rel_path in self._fs_snapshot:
                if rel_path not in current_snapshot:
                    changes.append((3, rel_path))
                    if rel_path in _CONFIG_FILE_NAMES:
                        config_changed = True
            self._fs_snapshot = current_snapshot
        else:
            self._fs_snapshot.update(current_snapshot)

        if config_changed:
            self._restart_language_server("Workspace configuration changed")
            return

        if not changes:
            return

        if len(changes) > _FS_SYNC_MAX_EVENTS:
            self._restart_language_server(f"Too many file changes ({len(changes)})")
            return

        payload = []
        for change_type, rel_path in changes:
            abs_path = (workspace_root / rel_path).absolute()
            payload.append({"uri": abs_path.as_uri(), "type": change_type})

        if payload:
            self._send_notification("workspace/didChangeWatchedFiles", {"changes": payload})

    def _sync_workspace_changes_best_effort(self) -> None:
        try:
            self._sync_workspace_changes()
        except Exception as e:
            logger.debug("Workspace file sync failed: %s", e)

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
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:  # nosec B110 - best-effort cleanup
                pass
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
        try:
            atexit.unregister(self._atexit_cleanup_handler)
        except Exception:  # nosec B110 - best-effort cleanup
            pass

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
        if "id" in msg and "method" in msg:
            self._handle_server_request(msg["id"], msg.get("method"), msg.get("params"))
            return

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
        process = self._process
        if not process or not process.stdin:
            raise LSPError("Language server not running")

        data = encode_message(content)
        try:
            with self._send_lock:
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
            try:
                self._send_notification("$/cancelRequest", {"id": req_id})
            except Exception:
                pass
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

    def workspace_symbols(self, query: str) -> list[SymbolInfo]:
        """Search for symbols by name across the workspace."""

        with self._request_lock:
            with self._lock:
                if not self._initialized:
                    raise LSPError("Language server not initialized")

            self._sync_workspace_changes_best_effort()
            result = self._send_request("workspace/symbol", {"query": query})
            return self._parse_symbol_info(result)

    def _parse_symbol_info(self, result: Any) -> list[SymbolInfo]:
        """Parse LSP SymbolInformation from response."""
        if not isinstance(result, list):
            return []

        symbols: list[SymbolInfo] = []
        for item in result:
            if not isinstance(item, dict):
                continue

            name = item.get("name", "")
            kind = item.get("kind", 0)
            location = item.get("location", {})
            uri = location.get("uri", "")
            rng = location.get("range", {})
            start = rng.get("start", {})
            container = item.get("containerName")

            if name and uri:
                symbols.append(
                    SymbolInfo(
                        name=name,
                        kind=kind,
                        uri=uri,
                        line=start.get("line", 0),
                        character=start.get("character", 0),
                        container_name=container,
                    )
                )

        return symbols

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
                return self._parse_document_symbols(result)
            finally:
                self._close_file(uri)

    def _parse_document_symbols(self, result: Any) -> list[DocumentSymbol]:
        """Parse LSP DocumentSymbol from response."""
        if not isinstance(result, list):
            return []

        def parse_item(item: dict[str, Any]) -> DocumentSymbol | None:
            if not isinstance(item, dict):
                return None
            name = item.get("name", "")
            kind = item.get("kind", 0)
            rng = item.get("range", {})
            start = rng.get("start", {})
            end = rng.get("end", {})

            if not name:
                return None

            children_raw = item.get("children", [])
            children = None
            if children_raw:
                parsed = [parse_item(c) for c in children_raw]
                children = [c for c in parsed if c is not None]

            return DocumentSymbol(
                name=name,
                kind=kind,
                range_start=start.get("line", 0),
                range_end=end.get("line", 0),
                children=children if children else None,
            )

        symbols = [parse_item(item) for item in result]
        return [s for s in symbols if s is not None]

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
                return self._parse_hover(result)
            finally:
                self._close_file(uri)

    def _parse_hover(self, result: Any) -> HoverInfo | None:
        """Parse LSP Hover response."""
        if not result or not isinstance(result, dict):
            return None

        contents = result.get("contents")
        if contents is None:
            return None

        # Handle MarkupContent
        if isinstance(contents, dict):
            value = contents.get("value", "")
            return HoverInfo(content=value) if value else None

        # Handle MarkedString (string variant)
        if isinstance(contents, str):
            return HoverInfo(content=contents) if contents else None

        # Handle MarkedString[] / MarkupContent[]
        if isinstance(contents, list):
            parts = []
            for item in contents:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("value", ""))
            combined = "\n\n".join(p for p in parts if p)
            return HoverInfo(content=combined) if combined else None

        return None

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
                item = self._parse_call_hierarchy_item(raw_item)
                if not item:
                    return []

                # Step 2: Get incoming or outgoing calls
                method = (
                    "callHierarchy/incomingCalls"
                    if direction == "incoming"
                    else "callHierarchy/outgoingCalls"
                )
                calls_result = self._send_request(method, {"item": raw_item})

                return self._parse_call_info_list(calls_result, direction)
            finally:
                self._close_file(uri)

    def _parse_call_hierarchy_item(self, raw: dict[str, Any]) -> CallHierarchyItem | None:
        """Parse a CallHierarchyItem from LSP response."""
        if not isinstance(raw, dict):
            return None

        name = raw.get("name", "")
        kind = raw.get("kind", 0)
        uri = raw.get("uri", "")
        rng = raw.get("range", {})
        sel = raw.get("selectionRange", {})

        if not name or not uri:
            return None

        return CallHierarchyItem(
            name=name,
            kind=kind,
            uri=uri,
            range_start_line=rng.get("start", {}).get("line", 0),
            range_start_char=rng.get("start", {}).get("character", 0),
            selection_start_line=sel.get("start", {}).get("line", 0),
            selection_start_char=sel.get("start", {}).get("character", 0),
        )

    def _parse_call_info_list(self, raw: Any, direction: str) -> list[CallInfo]:
        """Parse incoming/outgoing calls response."""
        if not isinstance(raw, list):
            return []

        results: list[CallInfo] = []
        for call in raw:
            if not isinstance(call, dict):
                continue

            # For incoming: "from" is the caller, "fromRanges" are call sites
            # For outgoing: "to" is the callee, "fromRanges" are call sites in current func
            item_key = "from" if direction == "incoming" else "to"
            raw_item = call.get(item_key)
            if not raw_item:
                continue

            item = self._parse_call_hierarchy_item(raw_item)
            if not item:
                continue

            from_ranges = []
            for rng in call.get("fromRanges", []):
                if isinstance(rng, dict):
                    start = rng.get("start", {})
                    from_ranges.append((start.get("line", 0), start.get("character", 0)))

            results.append(CallInfo(item=item, from_ranges=from_ranges))

        return results

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
        self._lease_counts: dict[str, int] = {}  # workspace -> active sessions
        self._max_clients = _parse_nonnegative_int_env_with_fallback(
            "SEARCH_LSP_MAX_CLIENTS", "RELACE_LSP_MAX_CLIENTS", 2
        )
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
            self._lease_counts.clear()

    def _pop_oldest_idle_client_locked(self) -> tuple[str, LSPClient] | None:
        for workspace in list(self._clients.keys()):
            if self._lease_counts.get(workspace, 0) != 0:
                continue
            client = self._clients.pop(workspace)
            self._lease_counts.pop(workspace, None)
            return (workspace, client)
        return None

    def _get_or_create_client_locked(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None,
        lease: bool,
    ) -> tuple[LSPClient, list[tuple[str, LSPClient]]]:
        existing = self._clients.get(workspace)
        if existing is not None:
            self._clients.pop(workspace, None)
            self._clients[workspace] = existing
            if lease:
                self._lease_counts[workspace] = self._lease_counts.get(workspace, 0) + 1
            else:
                self._lease_counts.setdefault(workspace, 0)
            return (existing, [])

        evicted: list[tuple[str, LSPClient]] = []
        if self._max_clients > 0:
            while len(self._clients) >= self._max_clients:
                popped = self._pop_oldest_idle_client_locked()
                if popped is None:
                    break
                evicted.append(popped)

        client = LSPClient(config, workspace, timeout_seconds=timeout_seconds)
        try:
            client.start()
        except Exception:
            for ws, c in evicted:
                self._clients[ws] = c
                self._lease_counts.setdefault(ws, 0)
            raise

        self._clients[workspace] = client
        self._lease_counts[workspace] = 1 if lease else 0
        return (client, evicted)

    @contextmanager
    def session(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None = None,
    ) -> "Generator[LSPClient, None, None]":
        """Acquire a leased LSP client for a workspace.

        A leased client is protected from LRU eviction while the session is
        active. The manager uses a soft cap: if all existing clients are leased,
        it may temporarily exceed SEARCH_LSP_MAX_CLIENTS until sessions are
        released and idle clients can be evicted.

        Args:
            config: Language server configuration.
            workspace: Workspace root path.
            timeout_seconds: Optional override for startup/request/shutdown timeouts.
        """
        clients_to_shutdown: list[LSPClient] = []
        with self._lock:
            client, evicted = self._get_or_create_client_locked(
                config,
                workspace,
                timeout_seconds=timeout_seconds,
                lease=True,
            )
            clients_to_shutdown = [c for _, c in evicted]

        for old_client in clients_to_shutdown:
            try:
                old_client.shutdown()
            except Exception:  # nosec B110 - best-effort cleanup
                pass

        try:
            yield client
        finally:
            clients_to_shutdown = []
            with self._lock:
                self._lease_counts[workspace] = max(0, self._lease_counts.get(workspace, 0) - 1)
                if self._max_clients > 0:
                    while len(self._clients) > self._max_clients:
                        popped = self._pop_oldest_idle_client_locked()
                        if popped is None:
                            break
                        clients_to_shutdown.append(popped[1])

            for old_client in clients_to_shutdown:
                try:
                    old_client.shutdown()
                except Exception:  # nosec B110 - best-effort cleanup
                    pass

    def get_client(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None = None,
    ) -> LSPClient:
        """Get or create a client for the given workspace."""
        clients_to_shutdown: list[LSPClient] = []
        client_to_return: LSPClient

        with self._lock:
            client, evicted = self._get_or_create_client_locked(
                config,
                workspace,
                timeout_seconds=timeout_seconds,
                lease=False,
            )
            client_to_return = client
            clients_to_shutdown = [c for _, c in evicted]

        for old_client in clients_to_shutdown:
            try:
                old_client.shutdown()
            except Exception:  # nosec B110 - best-effort cleanup
                pass

        return client_to_return
