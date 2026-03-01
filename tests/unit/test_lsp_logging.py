import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.lsp.logging import (
    log_lsp_client_created,
    log_lsp_client_evicted,
    log_lsp_request_error,
    log_lsp_server_error,
    log_lsp_server_start,
    log_lsp_server_stop,
)
from relace_mcp.observability.events import log_tool_complete, log_tool_start


class TestLSPServerLogging:
    def test_log_lsp_server_start_writes_event(self, mock_log_path: Path) -> None:
        log_lsp_server_start("python", "/tmp/workspace", ["basedpyright-langserver"], 1234.5)
        lines = mock_log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 1
        payload = json.loads(lines[0])
        assert payload["kind"] == "lsp_server_start"
        assert payload["language_id"] == "python"
        assert payload["latency_ms"] == 1234
        assert payload["level"] == "info"

    def test_log_lsp_server_start_writes_trace_event(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
        ):
            log_lsp_server_start("python", "/tmp/ws", ["cmd"], 100.0)
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        assert any(e["kind"] == "lsp_server_start" for e in events)
        trace_event = next(e for e in events if e["kind"] == "lsp_server_start")
        assert trace_event["command"] == ["cmd"]

    def test_log_lsp_server_stop_writes_event(self, mock_log_path: Path) -> None:
        log_lsp_server_stop("python", "/tmp/workspace")
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "lsp_server_stop"
        assert payload["language_id"] == "python"
        assert payload["level"] == "info"

    def test_log_lsp_server_error_writes_event(self, mock_log_path: Path) -> None:
        log_lsp_server_error("python", "/tmp/ws", "not found", "FileNotFoundError")
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "lsp_server_error"
        assert payload["level"] == "error"
        assert payload["error_type"] == "FileNotFoundError"

    def test_log_lsp_server_error_writes_trace_event(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
        ):
            log_lsp_server_error("go", "/tmp/ws", "crashed", "RuntimeError")
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        assert any(e["kind"] == "lsp_server_error" for e in events)


class TestLSPClientPoolLogging:
    def test_log_lsp_client_created(self, mock_log_path: Path) -> None:
        log_lsp_client_created("python", "/tmp/ws", 1)
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "lsp_client_created"
        assert payload["pool_size"] == 1
        assert payload["level"] == "info"

    def test_log_lsp_client_evicted(self, mock_log_path: Path) -> None:
        log_lsp_client_evicted("python", "/tmp/ws", 2, "pool_full")
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "lsp_client_evicted"
        assert payload["reason"] == "pool_full"
        assert payload["pool_size"] == 2
        assert payload["level"] == "info"


class TestLSPRequestErrorLogging:
    def test_log_lsp_request_error(self, mock_log_path: Path) -> None:
        log_lsp_request_error("workspace/configuration", "bad params", "ValueError")
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "lsp_request_error"
        assert payload["level"] == "warning"
        assert payload["method"] == "workspace/configuration"
        assert payload["error"] == "bad params"
        assert payload["error_type"] == "ValueError"


class TestToolStartCompleteDirectly:
    def test_log_tool_start_basic(self, mock_log_path: Path) -> None:
        log_tool_start("fast_apply")
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "tool_start"
        assert payload["tool"] == "fast_apply"
        assert payload["level"] == "debug"

    def test_log_tool_start_with_params(self, mock_log_path: Path) -> None:
        log_tool_start("fast_apply", {"file_path": "/repo/foo.py", "edit_snippet": "x" * 500})
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "tool_start"
        assert "params_keys" in payload
        assert set(payload["params_keys"]) == {"file_path", "edit_snippet"}
        assert "params_preview" in payload

    def test_log_tool_complete_basic(self, mock_log_path: Path) -> None:
        log_tool_complete("fast_apply", 123.4, ["status", "file_path"])
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "tool_complete"
        assert payload["tool"] == "fast_apply"
        assert payload["latency_ms"] == 123
        assert payload["result_keys"] == ["status", "file_path"]

    def test_log_tool_complete_no_result_keys(self, mock_log_path: Path) -> None:
        log_tool_complete("agentic_search", 50.0)
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "tool_complete"
        assert payload["result_keys"] is None


class TestLSPLoggingFilteredWhenDisabled:
    def test_lsp_events_not_written_when_logging_off(self, tmp_path: Path) -> None:
        log_path = tmp_path / "should_not_exist.log"
        with (
            patch("relace_mcp.config.settings.MCP_LOGGING", False),
            patch("relace_mcp.config.settings.LOG_PATH", log_path),
        ):
            log_lsp_server_start("python", "/tmp/ws", ["cmd"], 100.0)
            log_lsp_server_stop("python", "/tmp/ws")
            log_lsp_client_created("python", "/tmp/ws", 1)
        assert not log_path.exists()

    def test_trace_events_not_written_when_trace_off(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "should_not_exist.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", False),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
        ):
            log_lsp_server_start("python", "/tmp/ws", ["cmd"], 100.0)
        assert not trace_path.exists()


class TestEvictionNotLoggedOnStartupRollback:
    """Verify no lsp_client_evicted event when new client startup fails and evicted clients are restored."""

    def test_no_eviction_event_on_startup_failure(self, mock_log_path: Path) -> None:
        from relace_mcp.lsp.languages.base import LanguageServerConfig
        from relace_mcp.lsp.manager import LSPClientManager

        manager = LSPClientManager()
        manager._max_clients = 1

        # Pre-fill pool with a fake client so eviction is triggered.
        fake_existing = MagicMock()
        existing_key = ("/workspace", "python")
        manager._clients[existing_key] = fake_existing
        manager._lease_counts[existing_key] = 0

        config = LanguageServerConfig(
            language_id="typescript",
            file_extensions=(".ts",),
            command=["fake-langserver"],
        )

        # Make the new client's start() fail.
        failing_client = MagicMock()
        failing_client.start.side_effect = FileNotFoundError("fake-langserver not found")

        with patch.object(manager, "_new_client", return_value=failing_client):
            with pytest.raises(FileNotFoundError):
                manager._get_or_create_client_locked(
                    config, "/workspace", timeout_seconds=10, lease=True
                )

        # Evicted client should be restored.
        assert existing_key in manager._clients
        assert manager._clients[existing_key] is fake_existing

        # No eviction event should have been logged.
        if mock_log_path.exists():
            events = [
                json.loads(line) for line in mock_log_path.read_text(encoding="utf-8").splitlines()
            ]
            eviction_events = [e for e in events if e.get("kind") == "lsp_client_evicted"]
            assert eviction_events == [], (
                f"Expected no eviction events on rollback, got {eviction_events}"
            )
