import time
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from ..observability import (
    clear_context,
    log_tool_complete,
    log_tool_error,
    log_tool_start,
    log_trace_event,
    set_tool_context,
)


class ToolTracingMiddleware(Middleware):
    """Middleware that traces tool execution with timing and MCP protocol logging.

    Sends tool execution metrics to the client via MCP protocol logging,
    and writes structured events to local JSONL log when MCP_LOGGING=safe|full.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        tool_name = getattr(context.message, "name", "unknown")
        params = getattr(context.message, "arguments", None)

        tid = set_tool_context(tool_name)
        log_tool_start(tool_name, params)
        log_trace_event(
            {
                "kind": "mcp_tool_request",
                "trace_id": tid,
                "tool_name": tool_name,
                "arguments": params,
            }
        )

        start = time.perf_counter()
        try:
            result = await call_next(context)
            duration_ms = (time.perf_counter() - start) * 1000

            result_keys = list(result.keys()) if isinstance(result, dict) else None
            log_tool_complete(tool_name, duration_ms, result_keys)
            log_trace_event(
                {
                    "kind": "mcp_tool_response",
                    "trace_id": tid,
                    "tool_name": tool_name,
                    "latency_ms": round(duration_ms, 1),
                    "result": result,
                }
            )
            await self._log_to_client(context, tool_name, duration_ms, success=True)

            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            log_tool_error(tool_name, duration_ms, str(exc), type(exc).__name__)
            log_trace_event(
                {
                    "kind": "mcp_tool_exception",
                    "trace_id": tid,
                    "tool_name": tool_name,
                    "latency_ms": round(duration_ms, 1),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
            await self._log_to_client(
                context, tool_name, duration_ms, success=False, error=str(exc)
            )
            raise
        finally:
            clear_context()

    async def _log_to_client(
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
        except Exception:  # nosec B110
            pass
