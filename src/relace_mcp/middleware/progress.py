import asyncio
from contextlib import suppress
from typing import Any

from fastmcp.server.context import Context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

_HEARTBEAT_MESSAGES: dict[str, str] = {
    "fast_apply": "fast_apply in progress",
    "agentic_search": "agentic_search in progress",
    "agentic_retrieval": "agentic_retrieval in progress",
}


class ProgressHeartbeatMiddleware(Middleware):
    """Send periodic progress notifications during long-running tool calls."""

    def __init__(self, *, interval_seconds: float = 5.0) -> None:
        self._interval_seconds = interval_seconds

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        tool_name = getattr(context.message, "name", "")
        message = _HEARTBEAT_MESSAGES.get(tool_name)
        if not message:
            return await call_next(context)

        ctx = context.fastmcp_context
        if ctx is None:
            return await call_next(context)

        progress_task = asyncio.create_task(self._heartbeat(ctx, message=message))
        try:
            return await call_next(context)
        finally:
            progress_task.cancel()
            with suppress(asyncio.CancelledError):
                await progress_task

    async def _heartbeat(self, ctx: Context, *, message: str) -> None:
        while True:
            try:
                await ctx.report_progress(progress=0, total=1.0, message=message)
            except Exception:
                return
            await asyncio.sleep(self._interval_seconds)
