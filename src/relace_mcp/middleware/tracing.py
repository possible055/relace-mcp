import time
import traceback
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


def _classify_tool_result(result: Any) -> tuple[bool, str | None, str | None]:
    if not isinstance(result, dict):
        return True, None, None

    status = result.get("status")
    if status == "error":
        message = result.get("message") or result.get("error") or "Tool returned status=error"
        error_type = result.get("code") or result.get("error_type") or "ToolError"
        return False, str(message), str(error_type)

    error = result.get("error")
    if error:
        if result.get("partial") is True:
            error_type = result.get("error_type") or "PartialResult"
        else:
            error_type = result.get("error_type") or "ToolError"
        return False, str(error), str(error_type)

    return True, None, None


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
            success, error_message, error_type = _classify_tool_result(result)
            if success:
                log_tool_complete(tool_name, duration_ms, result_keys)
            else:
                log_tool_error(tool_name, duration_ms, error_message or "", error_type)
            log_trace_event(
                {
                    "kind": "mcp_tool_response",
                    "trace_id": tid,
                    "tool_name": tool_name,
                    "latency_ms": round(duration_ms, 1),
                    "success": success,
                    "error": error_message,
                    "error_type": error_type,
                    "result": result,
                }
            )
            await self._log_to_client(
                context,
                tool_name,
                duration_ms,
                success=success,
                error=error_message,
            )

            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            error_message = str(exc) or type(exc).__name__
            tb = traceback.format_exc()
            log_tool_error(
                tool_name,
                duration_ms,
                error_message,
                type(exc).__name__,
                traceback_str=tb,
            )
            log_trace_event(
                {
                    "kind": "mcp_tool_exception",
                    "trace_id": tid,
                    "tool_name": tool_name,
                    "latency_ms": round(duration_ms, 1),
                    "error": error_message,
                    "error_type": type(exc).__name__,
                    "traceback": tb,
                }
            )
            await self._log_to_client(
                context,
                tool_name,
                duration_ms,
                success=False,
                error=error_message,
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
