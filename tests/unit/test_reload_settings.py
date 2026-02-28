from collections.abc import Generator
from pathlib import Path

import pytest

import relace_mcp.config.settings as settings_mod
from relace_mcp.config.settings import reload_logging_settings

_RELOAD_KEYS = (
    "MCP_LOGGING_MODE",
    "MCP_LOGGING",
    "MCP_LOG_REDACT",
    "MCP_TRACE_LOGGING",
    "MCP_LOG_FILE_LEVEL",
    "MCP_LOG_INCLUDE_KINDS",
    "MCP_LOG_EXCLUDE_KINDS",
    "MCP_TRACE_INCLUDE_KINDS",
    "MCP_TRACE_EXCLUDE_KINDS",
    "LOG_DIR",
    "LOG_PATH",
    "TRACE_DIR",
    "TRACE_PATH",
)


@pytest.fixture(autouse=True)
def _restore_settings() -> Generator[None, None, None]:
    """Snapshot and restore settings globals that reload_logging_settings() mutates."""
    snapshot = {k: getattr(settings_mod, k) for k in _RELOAD_KEYS}
    yield
    for k, v in snapshot.items():
        setattr(settings_mod, k, v)


class TestReloadLoggingSettings:
    def test_reload_off_to_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOGGING", "full")
        monkeypatch.delenv("MCP_TRACE", raising=False)
        reload_logging_settings()

        assert settings_mod.MCP_LOGGING_MODE == "full"
        assert settings_mod.MCP_LOGGING is True
        assert settings_mod.MCP_LOG_REDACT is False
        assert settings_mod.MCP_TRACE_LOGGING is True

    def test_reload_to_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOGGING", "safe")
        reload_logging_settings()

        assert settings_mod.MCP_LOGGING_MODE == "safe"
        assert settings_mod.MCP_LOGGING is True
        assert settings_mod.MCP_LOG_REDACT is True
        assert settings_mod.MCP_TRACE_LOGGING is False

    def test_reload_to_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOGGING", "off")
        reload_logging_settings()

        assert settings_mod.MCP_LOGGING_MODE == "off"
        assert settings_mod.MCP_LOGGING is False

    def test_reload_updates_paths(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom_dir = str(tmp_path / "custom_logs")
        monkeypatch.setenv("MCP_LOG_DIR", custom_dir)
        monkeypatch.delenv("MCP_LOG_PATH", raising=False)
        monkeypatch.delenv("MCP_TRACE_DIR", raising=False)
        monkeypatch.delenv("MCP_TRACE_PATH", raising=False)
        monkeypatch.setenv("MCP_LOGGING", "safe")
        reload_logging_settings()

        assert settings_mod.LOG_DIR == Path(custom_dir)
        assert settings_mod.LOG_PATH == Path(custom_dir) / "relace.log"
        assert settings_mod.TRACE_DIR == Path(custom_dir) / "traces"

    def test_reload_updates_filter_kinds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOG_INCLUDE_KINDS", "tool_start,tool_complete")
        monkeypatch.setenv("MCP_TRACE_EXCLUDE_KINDS", "llm_request")
        monkeypatch.setenv("MCP_LOGGING", "safe")
        reload_logging_settings()

        assert settings_mod.MCP_LOG_INCLUDE_KINDS == frozenset({"tool_start", "tool_complete"})
        assert settings_mod.MCP_TRACE_EXCLUDE_KINDS == frozenset({"llm_request"})

    def test_reload_updates_file_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOG_FILE_LEVEL", "WARNING")
        monkeypatch.setenv("MCP_LOGGING", "safe")
        reload_logging_settings()

        assert settings_mod.MCP_LOG_FILE_LEVEL == "WARNING"

    def test_redact_value_reads_reloaded_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """redact_value() should observe MCP_LOG_REDACT changes after reload."""
        from relace_mcp.observability.events import redact_value

        long_value = "x" * 500

        # Redaction on (safe mode)
        monkeypatch.setenv("MCP_LOGGING", "safe")
        reload_logging_settings()
        assert settings_mod.MCP_LOG_REDACT is True
        assert len(redact_value(long_value, max_len=200)) <= 200

        # Redaction off (full mode)
        monkeypatch.setenv("MCP_LOGGING", "full")
        reload_logging_settings()
        assert settings_mod.MCP_LOG_REDACT is False
        assert redact_value(long_value, max_len=200) == long_value
