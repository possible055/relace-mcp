import json
from pathlib import Path
from unittest.mock import patch

from relace_mcp.observability import log_event, log_tool_error
from relace_mcp.observability.traces import log_trace_event


class TestEventLogFiltering:
    def test_filters_by_min_level(self, mock_log_path: Path) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_FILE_LEVEL", "ERROR"):
            log_event({"kind": "k_info", "level": "info"})
            log_event({"kind": "k_error", "level": "error"})

        lines = mock_log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["kind"] == "k_error"

    def test_filters_by_kind_include_list(self, mock_log_path: Path) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_INCLUDE_KINDS", frozenset({"keep"})):
            log_event({"kind": "drop", "level": "info"})
            log_event({"kind": "keep", "level": "info"})

        lines = mock_log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["kind"] == "keep"


class TestTraceLogFiltering:
    def test_filters_by_kind_include_list(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.config.settings.MCP_TRACE_INCLUDE_KINDS", frozenset({"keep"})),
            patch("relace_mcp.config.settings.MCP_TRACE_EXCLUDE_KINDS", frozenset()),
        ):
            log_trace_event({"kind": "drop", "x": 1})
            log_trace_event({"kind": "keep", "x": 2})

        lines = trace_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["kind"] == "keep"


class TestToolErrorTraceback:
    def test_includes_traceback_when_provided(self, mock_log_path: Path) -> None:
        log_tool_error(
            "agentic_search",
            12.3,
            "boom",
            "RuntimeError",
            traceback_str="Traceback (most recent call last):\n  ...\nRuntimeError: boom",
        )
        payload = json.loads(mock_log_path.read_text(encoding="utf-8").strip())
        assert payload["kind"] == "tool_error"
        assert payload.get("traceback")


class TestTraceLevelFiltering:
    def test_trace_filters_by_min_level(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.config.settings.MCP_LOG_FILE_LEVEL", "WARNING"),
            patch("relace_mcp.config.settings.MCP_TRACE_INCLUDE_KINDS", frozenset()),
            patch("relace_mcp.config.settings.MCP_TRACE_EXCLUDE_KINDS", frozenset()),
        ):
            log_trace_event({"kind": "llm_request"})  # inferred debug -> filtered
            log_trace_event({"kind": "llm_error"})  # inferred error -> kept
            log_trace_event(
                {"kind": "mcp_tool_response", "success": False}
            )  # inferred warning -> kept

        lines = trace_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        kinds = [json.loads(line)["kind"] for line in lines]
        assert "llm_error" in kinds
        assert "mcp_tool_response" in kinds

    def test_trace_infers_level_on_events(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.config.settings.MCP_LOG_FILE_LEVEL", "DEBUG"),
            patch("relace_mcp.config.settings.MCP_TRACE_INCLUDE_KINDS", frozenset()),
            patch("relace_mcp.config.settings.MCP_TRACE_EXCLUDE_KINDS", frozenset()),
        ):
            log_trace_event({"kind": "llm_request"})
            log_trace_event({"kind": "mcp_tool_exception"})
            log_trace_event({"kind": "mcp_tool_response", "success": False})
            log_trace_event({"kind": "mcp_tool_response", "success": True})

        lines = trace_path.read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines]
        assert events[0]["level"] == "debug"
        assert events[1]["level"] == "error"
        assert events[2]["level"] == "warning"
        assert events[3]["level"] == "debug"
