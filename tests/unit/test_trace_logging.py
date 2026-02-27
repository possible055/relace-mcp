import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import openai
import pytest

from relace_mcp.backend.openai_backend import OpenAIChatClient
from relace_mcp.config.provider import ProviderConfig
from relace_mcp.observability.traces import log_trace_event
from relace_mcp.repo.backends.cli import _run_cli_text


class TestTraceWriter:
    def test_log_trace_event_writes_json_line(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
        ):
            log_trace_event({"kind": "test_trace", "trace_id": "t1", "message": "hello"})

        assert trace_path.exists()
        logged = json.loads(trace_path.read_text(encoding="utf-8").strip())
        assert logged["kind"] == "test_trace"
        assert logged["trace_id"] == "t1"
        assert logged["message"] == "hello"
        assert "timestamp" in logged

    def test_log_trace_event_noop_when_disabled(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", False),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
        ):
            log_trace_event({"kind": "test_trace"})

        assert not trace_path.exists()

    def test_trace_rotation(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        trace_path.write_text("x" * 100, encoding="utf-8")

        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.config.settings.MAX_TRACE_LOG_SIZE_BYTES", 1),
        ):
            log_trace_event({"kind": "after_rotate", "trace_id": "t1"})

        assert trace_path.exists()
        assert "after_rotate" in trace_path.read_text(encoding="utf-8")
        rotated = list(tmp_path.glob("relace.trace.*.jsonl"))
        assert rotated


class TestCLILogTrace:
    def test_cli_text_tracing_writes_events(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        mock_result = MagicMock(returncode=0, stdout="ok", stderr="")

        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.repo.backends.cli.subprocess.run", return_value=mock_result),
        ):
            out = _run_cli_text(["codanna", "--version"], str(tmp_path), timeout=1)

        assert out == "ok"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        kinds = [e.get("kind") for e in events]
        assert "cli_request" in kinds
        assert "cli_response" in kinds


class TestLLMTrace:
    def test_llm_success_tracing_writes_events(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"choices": [{"message": {"content": "ok"}}]}

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.return_value = mock_response

        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.backend.openai_backend.OpenAI", return_value=mock_openai_client),
            patch("relace_mcp.backend.openai_backend.AsyncOpenAI", return_value=MagicMock()),
        ):
            client = OpenAIChatClient(
                ProviderConfig(
                    provider="openai",
                    api_compat="openai",
                    base_url="https://example.test/v1",
                    model="gpt-test",
                    api_key="sk-test",
                    timeout_seconds=1.0,
                    display_name="Openai",
                )
            )
            payload, _latency = client.chat_completions(
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.0,
                extra_body={"x": 1},
                trace_id="tid",
            )

        assert payload["choices"][0]["message"]["content"] == "ok"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        kinds = [e.get("kind") for e in events]
        assert "llm_request" in kinds
        assert "llm_response" in kinds

    def test_llm_error_tracing_writes_events(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "relace.trace.jsonl"
        bad_request = openai.BadRequestError(
            message="Bad request",
            response=MagicMock(status_code=400),
            body=None,
        )

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.side_effect = bad_request

        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", trace_path),
            patch("relace_mcp.backend.openai_backend.OpenAI", return_value=mock_openai_client),
            patch("relace_mcp.backend.openai_backend.AsyncOpenAI", return_value=MagicMock()),
        ):
            client = OpenAIChatClient(
                ProviderConfig(
                    provider="openai",
                    api_compat="openai",
                    base_url="https://example.test/v1",
                    model="gpt-test",
                    api_key="sk-test",
                    timeout_seconds=1.0,
                    display_name="Openai",
                )
            )
            with pytest.raises(openai.BadRequestError):
                client.chat_completions(
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=0.0,
                    extra_body=None,
                    trace_id="tid",
                )

        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        llm_errors = [e for e in events if e.get("kind") == "llm_error"]
        assert llm_errors
        assert llm_errors[-1].get("status_code") == 400


class TestRotationDynamicPattern:
    def test_event_rotation_custom_filename(self, tmp_path: Path) -> None:
        custom_log = tmp_path / "myapp.log"
        custom_log.write_text("x" * 100, encoding="utf-8")

        with (
            patch("relace_mcp.config.settings.MCP_LOGGING", True),
            patch("relace_mcp.config.settings.LOG_PATH", custom_log),
            patch("relace_mcp.config.settings.MAX_LOG_SIZE_BYTES", 1),
        ):
            from relace_mcp.observability import log_event

            log_event({"kind": "after_rotate", "level": "info"})

        assert custom_log.exists()
        rotated = list(tmp_path.glob("myapp.*.log"))
        assert rotated

    def test_trace_rotation_custom_filename(self, tmp_path: Path) -> None:
        custom_trace = tmp_path / "mytrace.jsonl"
        custom_trace.write_text("x" * 100, encoding="utf-8")

        with (
            patch("relace_mcp.config.settings.MCP_TRACE_LOGGING", True),
            patch("relace_mcp.config.settings.TRACE_PATH", custom_trace),
            patch("relace_mcp.config.settings.MAX_TRACE_LOG_SIZE_BYTES", 1),
        ):
            log_trace_event({"kind": "after_rotate", "trace_id": "t1"})

        assert custom_trace.exists()
        rotated = list(tmp_path.glob("mytrace.*.jsonl"))
        assert rotated
