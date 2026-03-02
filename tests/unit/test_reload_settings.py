from collections.abc import Generator

import pytest

import relace_mcp.config.settings as settings_mod
from relace_mcp.config.settings import reload_logging_settings

_RELOAD_KEYS = (
    "MCP_LOGGING_MODE",
    "MCP_LOGGING",
    "MCP_LOG_REDACT",
    "MCP_TRACE_LOGGING",
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

    def test_redact_value_reads_reloaded_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """redact_value() should observe MCP_LOG_REDACT changes after reload."""
        from relace_mcp.observability.events import redact_value

        long_value = "x" * 500

        # Redaction on (safe mode): always returns placeholder, never content
        monkeypatch.setenv("MCP_LOGGING", "safe")
        reload_logging_settings()
        assert settings_mod.MCP_LOG_REDACT is True
        result = redact_value(long_value, max_len=200)
        assert "REDACTED" in result
        assert "x" * 10 not in result

        # Redaction off (full mode): truncates to max_len
        monkeypatch.setenv("MCP_LOGGING", "full")
        reload_logging_settings()
        assert settings_mod.MCP_LOG_REDACT is False
        result_full = redact_value(long_value, max_len=200)
        assert len(result_full) <= 200
        assert result_full.startswith("x")
