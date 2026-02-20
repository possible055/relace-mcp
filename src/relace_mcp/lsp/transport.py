import concurrent.futures
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from relace_mcp.lsp.protocol import MessageBuffer, encode_message
from relace_mcp.lsp.types import LSPError

logger = logging.getLogger(__name__)


class JsonRpcTransport:
    """Thread-safe JSON-RPC transport over stdio."""

    def __init__(
        self,
        *,
        lock: threading.RLock,
        send_lock: threading.Lock,
        stop_event: threading.Event,
        on_server_request: Callable[[Any, Any, Any], None],
        read_chunk_size: int,
    ) -> None:
        self._lock = lock
        self._send_lock = send_lock
        self._stop_event = stop_event
        self._on_server_request = on_server_request
        self._read_chunk_size = read_chunk_size
        self._message_buffer = MessageBuffer()
        self._request_id = 0
        self._pending_requests: dict[int, concurrent.futures.Future[Any]] = {}

    def cancel_all_pending(self) -> None:
        with self._lock:
            pending = list(self._pending_requests.values())
            self._pending_requests.clear()

        for fut in pending:
            if not fut.done():
                fut.cancel()

    def fail_all_pending(self, error: Exception) -> None:
        with self._lock:
            pending = list(self._pending_requests.values())
            self._pending_requests.clear()

        for fut in pending:
            if fut.done():
                continue
            fut.set_exception(error)

    def clear_buffer(self) -> None:
        self._message_buffer.clear()

    def handle_message(self, msg: dict[str, Any]) -> None:
        if "id" in msg and "method" in msg:
            self._on_server_request(msg["id"], msg.get("method"), msg.get("params"))
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

    def read_stdout_loop(self, process: Any) -> None:
        if not process or not process.stdout:
            return

        try:
            fd = process.stdout.fileno()
            while not self._stop_event.is_set():
                data = os.read(fd, self._read_chunk_size)
                if not data:
                    break

                self._message_buffer.append(data)
                while True:
                    msg = self._message_buffer.try_parse_message()
                    if msg is None:
                        break
                    self.handle_message(msg)
        except Exception as e:
            logger.debug("LSP stdout reader stopped: %s", e)
        finally:
            if not self._stop_event.is_set():
                self.fail_all_pending(LSPError("Language server exited"))

    def drain_stderr_loop(self, process: Any) -> None:
        if not process or not process.stderr:
            return

        try:
            for line in iter(process.stderr.readline, b""):
                if not line:
                    break
                logger.debug("LSP stderr: %s", line.decode("utf-8", errors="replace").rstrip())
        except Exception:
            return

    def send_message(self, process: Any, content: dict[str, Any]) -> None:
        if not process or not process.stdin:
            raise LSPError("Language server not running")

        data = encode_message(content)
        try:
            with self._send_lock:
                process.stdin.write(data)
                process.stdin.flush()
        except BrokenPipeError as e:
            raise LSPError(f"Language server stdin closed: {e}") from e

    def send_notification(self, process: Any, method: str, params: dict[str, Any]) -> None:
        self.send_message(
            process,
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            },
        )

    def send_request(
        self,
        process: Any,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float,
    ) -> Any:
        with self._lock:
            if not process:
                raise LSPError("Language server not running")
            self._request_id += 1
            req_id = self._request_id
            future: concurrent.futures.Future[Any] = concurrent.futures.Future()
            self._pending_requests[req_id] = future

        try:
            self.send_message(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params,
                },
            )
        except Exception:
            with self._lock:
                self._pending_requests.pop(req_id, None)
            raise

        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            with self._lock:
                self._pending_requests.pop(req_id, None)
            try:
                self.send_notification(process, "$/cancelRequest", {"id": req_id})
            except Exception:  # nosec B110 - best-effort cancellation
                pass
            raise LSPError(f"Request {method} timed out") from None


__all__ = ["JsonRpcTransport"]
