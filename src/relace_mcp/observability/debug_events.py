from datetime import UTC, datetime
from typing import Any

from ..config.settings import MCP_DEBUG_MODE
from .context import get_call_chain
from .events import log_event


def _log_debug_event(event_type: str, trace_id: str, **kwargs: Any) -> None:
    """Log a debug event if debug mode is enabled."""
    if not MCP_DEBUG_MODE:
        return

    event: dict[str, Any] = {
        "kind": f"debug_{event_type}",
        "level": "debug",
        "trace_id": trace_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    event.update(kwargs)
    log_event(event)


def log_debug_tool_start(
    trace_id: str,
    tool_name: str,
    args: dict[str, Any],
    turn: int | None = None,
) -> None:
    """Log tool execution start with call chain."""
    _log_debug_event(
        "tool_start",
        trace_id,
        tool_name=tool_name,
        args=args,
        turn=turn,
        call_chain=get_call_chain(),
    )


def log_debug_tool_end(
    trace_id: str,
    tool_name: str,
    latency_ms: float,
    result_type: str = "unknown",
    result_size: int = 0,
) -> None:
    """Log tool execution end."""
    _log_debug_event(
        "tool_end",
        trace_id,
        tool_name=tool_name,
        latency_ms=round(latency_ms, 1),
        result_type=result_type,
        result_size=result_size,
    )


def log_debug_turn_start(
    trace_id: str,
    turn: int,
    context_chars: int,
    messages_count: int,
) -> None:
    """Log turn start state."""
    _log_debug_event(
        "turn_start",
        trace_id,
        turn=turn,
        context_chars=context_chars,
        messages_count=messages_count,
    )


def log_debug_turn_end(
    trace_id: str,
    turn: int,
    tools_executed: int,
    tool_names: list[str],
    turn_latency_ms: float,
) -> None:
    """Log turn completion."""
    _log_debug_event(
        "turn_end",
        trace_id,
        turn=turn,
        tools_executed=tools_executed,
        tool_names=tool_names,
        turn_latency_ms=round(turn_latency_ms, 1),
    )
