import logging
import os
from pathlib import Path
from typing import Any

from relace_mcp.lsp.events import log_lsp_request_error
from relace_mcp.lsp.types import LSPError

logger = logging.getLogger(__name__)


class LSPSession:
    """Handles LSP protocol handshake, document lifecycle, and server-initiated requests.

    Operates on a shared transport; does not own the process or threading primitives.
    """

    def __init__(
        self,
        config: Any,
        workspace: str,
        workspace_settings: dict[str, Any],
        send_request_fn: Any,
        send_notification_fn: Any,
        send_response_fn: Any,
        send_error_response_fn: Any,
    ) -> None:
        self._config = config
        self._workspace = workspace
        self._workspace_settings = workspace_settings
        self._send_request = send_request_fn
        self._send_notification = send_notification_fn
        self._send_response = send_response_fn
        self._send_error_response = send_error_response_fn

    def initialize(self, startup_timeout: float) -> None:
        """Send LSP initialize + initialized handshake."""
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
                    "workspaceFolders": False,
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [{"uri": workspace_uri, "name": Path(self._workspace).name}],
        }

        if self._config.initialization_options:
            params["initializationOptions"] = self._config.initialization_options

        self._send_request("initialize", params, timeout=startup_timeout)
        self._send_notification("initialized", {})
        self._send_notification(
            "workspace/didChangeConfiguration",
            {"settings": self._workspace_settings},
        )

    def open_file(self, file_path: str) -> str:
        """Open a file in the language server and return its URI.

        Args:
            file_path: Relative path within the workspace.

        Returns:
            File URI sent to the language server.
        """
        if os.path.isabs(file_path):
            raise LSPError(f"Absolute path not allowed: {file_path}")

        target = Path(self._workspace) / file_path
        if target.is_symlink():
            raise LSPError(f"Symlinks not allowed: {file_path}")

        try:
            abs_path = target.resolve()
            workspace_resolved = Path(self._workspace).resolve()
        except (OSError, RuntimeError) as e:
            raise LSPError(f"Invalid path: {e}") from e

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

    def close_file(self, uri: str) -> None:
        """Close a file in the language server."""
        self._send_notification("textDocument/didClose", {"textDocument": {"uri": uri}})

    def get_settings_section(self, section: Any) -> Any:
        if not section or not isinstance(section, str):
            return self._workspace_settings

        current: Any = self._workspace_settings
        for part in section.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def handle_server_request(self, req_id: Any, method: Any, params: Any) -> None:
        """Dispatch server-initiated requests back to the client."""
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
                        results.append(self.get_settings_section(section))

                self._send_response(req_id, results)
                return

            self._send_error_response(req_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            logger.debug(
                "Failed to handle server request method=%s",
                method if isinstance(method, str) else "<invalid>",
                exc_info=True,
            )
            log_lsp_request_error(
                method if isinstance(method, str) else "<unknown>",
                str(exc),
                type(exc).__name__,
            )
            try:
                self._send_error_response(req_id, -32603, "Internal error")
            except Exception:
                return
