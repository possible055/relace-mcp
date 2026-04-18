from unittest.mock import patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

_TOOLS_MOD = "relace_mcp.tools.mcp_status"


pytestmark = pytest.mark.usefixtures("clean_env")


def _make_config(tmp_path) -> RelaceConfig:
    return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["relace", "codanna", "chunkhound"])
async def test_index_status_returns_only_active_backend(
    tmp_path, monkeypatch, backend: str
) -> None:
    monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", backend)
    config = _make_config(tmp_path)

    with patch(f"{_TOOLS_MOD}.shutil.which", return_value="/usr/local/bin/fake"):
        server = build_server(config=config, run_health_check=False)

        from fastmcp import Client

        async with Client(server) as client:
            result = await client.call_tool("index_status", {})

    payload = result.structured_content
    assert payload is not None
    assert payload["active_backend"] == backend
    assert set(payload) == {
        "trace_id",
        "base_dir",
        "base_dir_source",
        "active_backend",
        "backend",
        "background_monitor",
    }
    assert "relace" not in payload
    assert "codanna" not in payload
    assert "chunkhound" not in payload

    backend_payload = payload["backend"]
    assert "freshness" in backend_payload
    assert "hints_usable" in backend_payload
    if backend == "relace":
        assert "sync_state" in backend_payload
        assert "status" in backend_payload
    else:
        assert "cli_path" in backend_payload
        assert set(backend_payload) == {"cli_path", "freshness", "hints_usable"}

    background_monitor = payload["background_monitor"]
    assert "state" in background_monitor
    assert "reason" in background_monitor
    assert "interval_seconds" in background_monitor
    assert "initial_delay_seconds" in background_monitor


@pytest.mark.asyncio
async def test_index_status_local_backend_with_missing_cli_is_read_only(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "codanna")
    config = _make_config(tmp_path)

    with patch(f"{_TOOLS_MOD}.shutil.which", return_value=None):
        server = build_server(config=config, run_health_check=False)

        from fastmcp import Client

        async with Client(server) as client:
            result = await client.call_tool("index_status", {})
            tools = await client.list_tools()

    payload = result.structured_content
    assert payload is not None
    assert payload["active_backend"] == "codanna"
    assert payload["backend"]["cli_path"] is None
    assert payload["backend"]["hints_usable"] is False

    status_tool = next(tool for tool in tools if tool.name == "index_status")
    assert status_tool.annotations is not None
    assert status_tool.annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_index_status_hidden_when_backend_is_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "none")
    config = _make_config(tmp_path)
    server = build_server(config=config, run_health_check=False)

    from fastmcp import Client

    async with Client(server) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}

    assert "index_status" not in tool_names
