import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server


@pytest.mark.usefixtures("clean_env")
def test_server_build_success(tmp_path):
    """Verify that build_server can successfully create an instance."""
    config = RelaceConfig(api_key="rlc-smoke-test", base_dir=str(tmp_path))
    # Disable health check to avoid excessive IO during smoke tests
    mcp = build_server(config, run_health_check=False)

    assert mcp is not None
    assert mcp.name == "Relace Fast Apply MCP"
