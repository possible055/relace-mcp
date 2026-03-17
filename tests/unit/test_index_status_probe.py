"""Regression tests for index_status auto-refresh scheduling (P2).

Verifies that index_status always schedules background refresh for stale/missing local
backends regardless of MCP_RETRIEVAL_BACKEND value.
"""

from unittest.mock import patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

_TOOLS_MOD = "relace_mcp.tools.mcp_search"


def _make_config(tmp_path) -> RelaceConfig:
    return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))


@pytest.mark.parametrize(
    "retrieval_backend",
    ["auto", "relace", "none", "codanna", "chunkhound"],
)
@pytest.mark.asyncio
async def test_refresh_scheduled_when_stale_on_any_retrieval_backend(
    tmp_path, retrieval_backend: str
) -> None:
    """index_status should schedule background refresh for stale local backends,
    regardless of MCP_RETRIEVAL_BACKEND.
    """
    config = _make_config(tmp_path)

    # Create stale local indexes with artifacts present but marker absent.
    codanna_index_dir = tmp_path / ".codanna" / "index" / "semantic"
    codanna_index_dir.mkdir(parents=True)
    (codanna_index_dir / "metadata.json").write_text("{}")
    chunkhound_dir = tmp_path / ".chunkhound"
    chunkhound_dir.mkdir()
    (chunkhound_dir / "db").write_bytes(b"index")

    with (
        patch(f"{_TOOLS_MOD}._settings") as mock_settings,
        patch(f"{_TOOLS_MOD}.shutil.which", return_value="/usr/local/bin/fake"),
        patch(f"{_TOOLS_MOD}.schedule_bg_codanna_full_index") as mock_codanna_refresh,
        patch(f"{_TOOLS_MOD}.schedule_bg_chunkhound_index") as mock_chunkhound_refresh,
    ):
        mock_settings.RETRIEVAL_BACKEND = retrieval_backend
        mock_settings.RELACE_CLOUD_TOOLS = False
        mock_settings.AGENTIC_RETRIEVAL_ENABLED = False

        server = build_server(config=config)

        from fastmcp import Client

        async with Client(server) as client:
            result = await client.call_tool("index_status", {})

    payload = result.structured_content
    assert payload is not None

    for backend in ("codanna", "chunkhound"):
        scheduled = payload[backend]["background_refresh_scheduled"]
        assert scheduled is True, f"{backend}.background_refresh_scheduled must be True"

    mock_codanna_refresh.assert_called_once_with(str(tmp_path))
    mock_chunkhound_refresh.assert_called_once_with(str(tmp_path))


@pytest.mark.asyncio
async def test_no_refresh_when_cli_missing(tmp_path) -> None:
    """When CLI is not found, background_refresh_scheduled must be False."""
    config = _make_config(tmp_path)

    with (
        patch(f"{_TOOLS_MOD}._settings") as mock_settings,
        patch(f"{_TOOLS_MOD}.shutil.which", return_value=None),
    ):
        mock_settings.RETRIEVAL_BACKEND = "auto"
        mock_settings.RELACE_CLOUD_TOOLS = False
        mock_settings.AGENTIC_RETRIEVAL_ENABLED = False

        server = build_server(config=config)

        from fastmcp import Client

        async with Client(server) as client:
            result = await client.call_tool("index_status", {})

    payload = result.structured_content
    for backend in ("codanna", "chunkhound"):
        assert payload[backend]["background_refresh_scheduled"] is False, (
            f"{backend}: expected False when CLI missing, got "
            f"{payload[backend]['background_refresh_scheduled']!r}"
        )
        assert payload[backend]["hints_usable"] is False, (
            f"{backend}: hints_usable must be False when CLI missing"
        )
