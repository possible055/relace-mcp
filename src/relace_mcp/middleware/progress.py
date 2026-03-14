import asyncio
from contextlib import suppress
from typing import Any

from fastmcp.server.context import Context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

_HEARTBEAT_TOOLS: frozenset[str] = frozenset({"fast_apply"})


class ProgressHeartbeatMiddleware(Middleware):
    """Send periodic indeterminate progress notifications for fast tools."""

    def __init__(self, *, interval_seconds: float = 5.0) -> None:
        self._interval_seconds = interval_seconds

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        tool_name = getattr(context.message, "name", "")
        if tool_name not in _HEARTBEAT_TOOLS:
            return await call_next(context)

        ctx = context.fastmcp_context
        if ctx is None:
            return await call_next(context)

        progress_task = asyncio.create_task(
            self._heartbeat(ctx, message=f"{tool_name} in progress")
        )
        try:
            return await call_next(context)
        finally:
            progress_task.cancel()
            with suppress(asyncio.CancelledError):
                await progress_task

    async def _heartbeat(self, ctx: Context, *, message: str) -> None:
        tick = 0
        while True:
            try:
                await ctx.report_progress(progress=tick, total=None, message=message)
                tick += 1
            except Exception:
                return
            await asyncio.sleep(self._interval_seconds)
