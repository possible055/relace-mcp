import logging
from typing import Any

from fastmcp.server.context import Context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

_CLOUD_VISIBILITY_INITIALIZED_KEY = "relace.cloud_visibility.initialized"


class CloudVisibilityMiddleware(Middleware):
    """Enable cloud-tagged components for a session when allowed.

    Cloud components are registered unconditionally but disabled globally via
    `mcp.disable(tags={"cloud"})`. This middleware enables them for a given
    session when `cloud_tools_enabled=True`.
    """

    def __init__(self, *, cloud_tools_enabled: bool) -> None:
        self._cloud_tools_enabled = cloud_tools_enabled

    async def _ensure_cloud_visibility(self, ctx: Context | None) -> None:
        if not self._cloud_tools_enabled:
            return
        if ctx is None:
            return

        try:
            if await ctx.get_state(_CLOUD_VISIBILITY_INITIALIZED_KEY):
                return
        except Exception:  # noqa: BLE001  # state miss on first call is expected
            logger.debug("Cloud visibility state not yet initialized")

        try:
            await ctx.enable_components(tags={"cloud"})
            await ctx.set_state(_CLOUD_VISIBILITY_INITIALIZED_KEY, True)
        except Exception as exc:
            logger.debug("Failed to enable cloud components: %s", exc)

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        await self._ensure_cloud_visibility(context.fastmcp_context)
        return await call_next(context)

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        await self._ensure_cloud_visibility(context.fastmcp_context)
        return await call_next(context)

    async def on_list_resources(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        await self._ensure_cloud_visibility(context.fastmcp_context)
        return await call_next(context)

    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        await self._ensure_cloud_visibility(context.fastmcp_context)
        return await call_next(context)
