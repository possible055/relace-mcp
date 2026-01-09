import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server


def test_server_build_success(tmp_path, clean_env):
    """Verify that build_server can successfully create an instance."""
    config = RelaceConfig(api_key="rlc-smoke-test", base_dir=str(tmp_path))
    # Disable health check to avoid excessive IO during smoke tests
    mcp = build_server(config, run_health_check=False)

    assert mcp is not None
    assert mcp.name == "Relace Fast Apply MCP"


@pytest.mark.asyncio
async def test_tool_registration(tmp_path, clean_env):
    """Verify that core tools are registered."""
    config = RelaceConfig(api_key="rlc-smoke-test", base_dir=str(tmp_path))
    mcp = build_server(config, run_health_check=False)

    # FastMCP's get_tool is usually asynchronous
    # Here we only test basic required tools; cloud tools depend on configuration
    target_tools = ["fast_apply", "fast_search"]
    from relace_mcp.config.settings import RELACE_CLOUD_TOOLS

    if RELACE_CLOUD_TOOLS:
        target_tools.append("cloud_sync")

    for name in target_tools:
        try:
            tool = await mcp.get_tool(name)
            assert tool.name == name
        except (AttributeError, KeyError, Exception):
            pytest.fail(f"Tool {name} was not registered correctly")
