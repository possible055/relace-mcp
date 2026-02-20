import threading
import time
from pathlib import Path

import pytest

from relace_mcp.lsp.process_runtime import resolve_server_command
from relace_mcp.lsp.transport import JsonRpcTransport
from relace_mcp.lsp.types import LSPError


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        return


class _FakeProcess:
    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None


class TestResolveServerCommand:
    def test_accepts_existing_explicit_path(self, tmp_path: Path) -> None:
        executable = tmp_path / "lsp-server"
        executable.write_text("binary", encoding="utf-8")

        cmd = resolve_server_command([str(executable), "--stdio"], "")
        assert cmd == [str(executable), "--stdio"]

    def test_resolves_from_which(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/lsp" if name == "lsp" else None)

        cmd = resolve_server_command(["lsp", "--stdio"], "")
        assert cmd == ["/usr/bin/lsp", "--stdio"]

    def test_reports_install_hint_on_missing_executable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)

        with pytest.raises(LSPError, match="Install with: pip install test-lsp"):
            resolve_server_command(["missing-lsp"], "pip install test-lsp")


class TestJsonRpcTransport:
    def _new_transport(self, callback: list[tuple[object, object, object]]) -> JsonRpcTransport:
        return JsonRpcTransport(
            lock=threading.RLock(),
            send_lock=threading.Lock(),
            stop_event=threading.Event(),
            on_server_request=lambda req_id, method, params: callback.append(
                (req_id, method, params)
            ),
            read_chunk_size=8192,
        )

    def test_dispatches_server_request_message(self) -> None:
        calls: list[tuple[object, object, object]] = []
        transport = self._new_transport(calls)

        transport.handle_message({"id": 7, "method": "workspace/configuration", "params": {"x": 1}})
        assert calls == [(7, "workspace/configuration", {"x": 1})]

    def test_send_request_timeout_sends_cancel_notification(self) -> None:
        calls: list[tuple[object, object, object]] = []
        transport = self._new_transport(calls)
        process = _FakeProcess()

        with pytest.raises(LSPError, match="Request test/method timed out"):
            transport.send_request(process, "test/method", {"k": "v"}, timeout=0.01)

        payload = b"".join(process.stdin.writes).decode("utf-8", errors="replace")
        assert '"method": "$/cancelRequest"' in payload

    def test_send_request_receives_response(self) -> None:
        calls: list[tuple[object, object, object]] = []
        transport = self._new_transport(calls)
        process = _FakeProcess()
        result_holder: dict[str, object] = {}

        def run_request() -> None:
            result_holder["result"] = transport.send_request(
                process,
                "workspace/symbol",
                {"query": "x"},
                timeout=1.0,
            )

        thread = threading.Thread(target=run_request)
        thread.start()

        for _ in range(50):
            if process.stdin.writes:
                break
            time.sleep(0.01)

        transport.handle_message({"id": 1, "result": [{"name": "X"}]})
        thread.join(timeout=2.0)

        assert result_holder["result"] == [{"name": "X"}]
