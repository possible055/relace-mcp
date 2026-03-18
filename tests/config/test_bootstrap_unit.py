from collections.abc import Generator
from pathlib import Path

import pytest

import relace_mcp.config.settings as settings_mod
from relace_mcp.config.bootstrap import initialize_runtime_from_env

_SNAPSHOT_KEYS = (
    "RELACE_CLOUD_TOOLS",
    "SEARCH_MAX_TURNS",
    "MCP_LOG_LEVEL",
    "SEARCH_PROVIDER",
    "SEARCH_ENDPOINT",
    "SEARCH_MODEL",
)


@pytest.fixture(autouse=True)
def _restore_settings() -> Generator[None, None, None]:
    snapshot = {k: getattr(settings_mod, k) for k in _SNAPSHOT_KEYS}
    yield
    for k, v in snapshot.items():
        setattr(settings_mod, k, v)


def test_initialize_runtime_from_env_loads_explicit_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "relace.env"
    env_file.write_text(
        "\n".join(
            [
                "RELACE_CLOUD_TOOLS=1",
                "SEARCH_MAX_TURNS=9",
                "MCP_LOG_LEVEL=debug",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("RELACE_CLOUD_TOOLS", raising=False)
    monkeypatch.delenv("SEARCH_MAX_TURNS", raising=False)
    monkeypatch.delenv("MCP_LOG_LEVEL", raising=False)
    monkeypatch.setenv("MCP_DOTENV_PATH", str(env_file))

    initialize_runtime_from_env()

    assert settings_mod.RELACE_CLOUD_TOOLS is True
    assert settings_mod.SEARCH_MAX_TURNS == 9
    assert settings_mod.MCP_LOG_LEVEL == "DEBUG"


def test_initialize_runtime_from_env_keeps_process_env_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "relace.env"
    env_file.write_text(
        "\n".join(
            [
                "SEARCH_PROVIDER=openai",
                "SEARCH_ENDPOINT=https://api.openai.com/v1",
                "SEARCH_MODEL=gpt-4o",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("MCP_DOTENV_PATH", str(env_file))

    initialize_runtime_from_env()

    assert settings_mod.SEARCH_PROVIDER == "openrouter"
    assert settings_mod.SEARCH_ENDPOINT == "https://api.openai.com/v1"
    assert settings_mod.SEARCH_MODEL == "gpt-4o"
