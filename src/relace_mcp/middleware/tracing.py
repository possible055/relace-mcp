import time
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


class ToolTracingMiddleware(Middleware):
    """Middleware that traces tool execution with timing and MCP protocol logging.

    Sends tool execution metrics to the client via MCP protocol logging,
    enabling observability in Claude Desktop and other MCP clients.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        tool_name = getattr(context.message, "name", "unknown")
        start = time.perf_counter()
        try:
            result = await call_next(context)
            duration_ms = (time.perf_counter() - start) * 1000
            await self._log_execution(context, tool_name, duration_ms, success=True)
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._log_execution(
                context, tool_name, duration_ms, success=False, error=str(exc)
            )
            raise

    async def _log_execution(
        self,
        context: MiddlewareContext[Any],
        tool_name: str,
        duration_ms: float,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        try:
            ctx = context.fastmcp_context
            if ctx is None:
                return

            status = "ok" if success else f"error: {error}"
            message = f"[{tool_name}] {status} ({duration_ms:.0f}ms)"

            if hasattr(ctx, "debug"):
                await ctx.debug(message)
        except Exception:
            pass
