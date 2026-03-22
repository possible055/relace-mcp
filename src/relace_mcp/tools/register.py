# pyright: reportUnusedFunction=false
# Decorator-registered functions (@mcp.tool, @mcp.resource) are accessed by the framework
from fastmcp import FastMCP

from ..config import RelaceConfig
from ..config import settings as _settings
from ._clients import ToolClients
from ._registry import ToolRegistryDeps
from ._setup import EncodingState
from .mcp_apply import register_apply_tools
from .mcp_cloud import register_cloud_components
from .mcp_search import register_search_tools
from .mcp_status import register_status_tools

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""
    deps = ToolRegistryDeps(
        config=config,
        clients=ToolClients(config),
        encoding_state=EncodingState(),
    )

    register_apply_tools(mcp, deps)
    register_search_tools(mcp, deps)
    register_status_tools(mcp, deps)
    if _settings.RELACE_CLOUD_TOOLS:
        register_cloud_components(mcp, deps)
