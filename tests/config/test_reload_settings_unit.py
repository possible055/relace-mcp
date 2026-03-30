from collections.abc import Generator

import pytest

import relace_mcp.config.settings as settings_mod
from relace_mcp.config.settings import (
    reload_logging_settings,
    reload_settings_from_env,
    reload_tool_settings,
)

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
    "SEARCH_PROVIDER",
    "SEARCH_API_KEY",
    "SEARCH_ENDPOINT",
    "SEARCH_MODEL",
    "SEARCH_PROMPT_FILE",
    "RETRIEVAL_PROMPT_FILE",
    "SEARCH_TIMEOUT_SECONDS",
    "SEARCH_TEMPERATURE",
    "SEARCH_BASH_TOOLS",
    "SEARCH_LSP_TOOLS",
    "SEARCH_TOOL_STRICT",
    "SEARCH_MAX_TURNS",
    "SEARCH_PARALLEL_TOOL_CALLS",
    "SEARCH_TOP_P",
    "SEARCH_LSP_TIMEOUT_SECONDS",
    "SEARCH_LSP_MAX_CLIENTS",
    "SEARCH_TURN_STATUS_MODE",
    "MCP_BACKGROUND_INDEX_MONITOR",
    "MCP_BACKGROUND_INDEX_INTERVAL_SECONDS",
    "MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS",
    "RELACE_UPLOAD_MAX_WORKERS",
    "RELACE_API_KEY",
    "MCP_BASE_DIR",
    "MCP_EXTRA_PATHS",
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

    def test_search_bash_tools_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_BASH_TOOLS", "true")
        reload_tool_settings()

        assert settings_mod.SEARCH_BASH_TOOLS is True

    def test_search_lsp_tools_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_LSP_TOOLS", "true")
        reload_tool_settings()

        assert settings_mod.SEARCH_LSP_TOOLS is True

    def test_search_turn_status_mode_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_SEARCH_TURN_STATUS_MODE", raising=False)
        reload_tool_settings()

        assert settings_mod.SEARCH_TURN_STATUS_MODE == "always"

    def test_search_turn_status_mode_reloaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SEARCH_TURN_STATUS_MODE", "final-only")
        reload_tool_settings()

        assert settings_mod.SEARCH_TURN_STATUS_MODE == "final-only"

    def test_search_turn_status_mode_invalid_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SEARCH_TURN_STATUS_MODE", "sometimes")

        with pytest.raises(RuntimeError, match="Invalid MCP_SEARCH_TURN_STATUS_MODE"):
            reload_tool_settings()

    def test_background_index_monitor_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_BACKGROUND_INDEX_MONITOR", "true")
        reload_tool_settings()

        assert settings_mod.MCP_BACKGROUND_INDEX_MONITOR is True

    def test_background_index_interval_reloaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_BACKGROUND_INDEX_INTERVAL_SECONDS", "480")
        monkeypatch.setenv("MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS", "45")
        reload_tool_settings()

        assert settings_mod.MCP_BACKGROUND_INDEX_INTERVAL_SECONDS == 480
        assert settings_mod.MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS == 45

    def test_background_index_interval_invalid_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_BACKGROUND_INDEX_INTERVAL_SECONDS", "0")
        monkeypatch.setenv("MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS", "bad")
        reload_tool_settings()

        assert settings_mod.MCP_BACKGROUND_INDEX_INTERVAL_SECONDS == 300
        assert settings_mod.MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS == 30

    def test_search_tool_strict_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_TOOL_STRICT", "false")
        reload_tool_settings()

        assert settings_mod.SEARCH_TOOL_STRICT is False

    def test_search_max_turns_reloaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_MAX_TURNS", "7")
        reload_tool_settings()

        assert settings_mod.SEARCH_MAX_TURNS == 7

    def test_search_max_turns_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_MAX_TURNS", "0")
        reload_tool_settings()

        assert settings_mod.SEARCH_MAX_TURNS == 6

    def test_search_lsp_timeout_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_LSP_TIMEOUT_SECONDS", "not-a-number")
        reload_settings_from_env()

        assert settings_mod.SEARCH_LSP_TIMEOUT_SECONDS == 15.0

    def test_search_temperature_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_TEMPERATURE", "not-a-number")
        reload_settings_from_env()

        assert settings_mod.SEARCH_TEMPERATURE == 1.0

    def test_search_top_p_invalid_falls_back_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_TOP_P", "bad")
        reload_settings_from_env()

        assert settings_mod.SEARCH_TOP_P is None

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
