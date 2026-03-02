from unittest.mock import patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server


@pytest.mark.asyncio
async def test_tool_timeouts(tmp_path) -> None:
    server = build_server(
        config=RelaceConfig(api_key="test-api-key", base_dir=str(tmp_path)),
        run_health_check=False,
    )

    expected = {
        "fast_apply": 300.0,
        "agentic_search": 600.0,
        "indexing_status": 120.0,
        "cloud_sync": 900.0,
        "cloud_search": 300.0,
        "cloud_clear": 300.0,
        "cloud_list": 120.0,
        "cloud_info": 300.0,
    }

    for name, timeout in expected.items():
        tool = await server.local_provider.get_tool(name)
        assert tool is not None
        assert tool.timeout == timeout


@pytest.mark.asyncio
async def test_agentic_retrieval_timeout(tmp_path) -> None:
    with (
        patch("relace_mcp.tools.AGENTIC_RETRIEVAL_ENABLED", True),
        patch("relace_mcp.tools.RETRIEVAL_BACKEND", "relace"),
    ):
        server = build_server(
            config=RelaceConfig(api_key="test-api-key", base_dir=str(tmp_path)),
            run_health_check=False,
        )

    tool = await server.local_provider.get_tool("agentic_retrieval")
    assert tool is not None
    assert tool.timeout == 900.0
