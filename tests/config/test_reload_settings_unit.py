from collections.abc import Generator

import pytest

import relace_mcp.config.settings as settings_mod
from relace_mcp.config.settings import reload_logging_settings, reload_tool_settings

_RELOAD_KEYS = (
    "MCP_LOGGING_MODE",
    "MCP_LOGGING",
    "MCP_LOG_REDACT",
    "MCP_TRACE_LOGGING",
)

_TOOL_RELOAD_KEYS = (
    "RELACE_CLOUD_TOOLS",
    "RETRIEVAL_BACKEND",
    "RETRIEVAL_HINT_POLICY",
    "AGENTIC_RETRIEVAL_ENABLED",
)


@pytest.fixture(autouse=True)
def _restore_settings() -> Generator[None, None, None]:
    """Snapshot and restore settings globals that reload functions mutate."""
    all_keys = _RELOAD_KEYS + _TOOL_RELOAD_KEYS
    snapshot = {k: getattr(settings_mod, k) for k in all_keys}
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


class TestReloadToolSettings:
    def test_cloud_tools_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "true")
        reload_tool_settings()

        assert settings_mod.RELACE_CLOUD_TOOLS is True

    def test_cloud_tools_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "false")
        reload_tool_settings()

        assert settings_mod.RELACE_CLOUD_TOOLS is False

    def test_retrieval_backend_codanna(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "codanna")
        reload_tool_settings()

        assert settings_mod.RETRIEVAL_BACKEND == "codanna"

    def test_retrieval_backend_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "auto")
        reload_tool_settings()

        assert settings_mod.RETRIEVAL_BACKEND == "auto"

    def test_agentic_retrieval_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "true")
        reload_tool_settings()

        assert settings_mod.AGENTIC_RETRIEVAL_ENABLED is True

    def test_retrieval_hint_policy_strict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_HINT_POLICY", "strict")
        reload_tool_settings()

        assert settings_mod.RETRIEVAL_HINT_POLICY == "strict"

    def test_module_attribute_access_sees_reloaded_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Accessing settings via module reference must see reloaded values."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "true")
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "chunkhound")
        reload_tool_settings()

        from relace_mcp.config import settings as _settings

        assert _settings.RELACE_CLOUD_TOOLS is True
        assert _settings.RETRIEVAL_BACKEND == "chunkhound"
