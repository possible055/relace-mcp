from typing import Any

from ..apply.logging import log_event

# ============ Public API ============


def log_search_start(trace_id: str, query: str) -> None:
    """Record search start event."""
    q = query or ""
    log_event(
        {
            "kind": "search_start",
            "trace_id": trace_id,
            "query_preview": q[:500] if len(q) > 500 else q,
        }
    )


def log_search_turn(
    trace_id: str,
    turn: int,
    max_turns: int,
    chars_used: int,
    tool_calls_count: int,
) -> None:
    """Record agent loop turn state."""
    log_event(
        {
            "kind": "search_turn",
            "trace_id": trace_id,
            "turn": turn,
            "max_turns": max_turns,
            "chars_used": chars_used,
            "tool_calls_count": tool_calls_count,
        }
    )


def log_tool_call(
    trace_id: str,
    tool_name: str,
    args: dict[str, Any],
    result_preview: str,
    latency_ms: float,
    success: bool,
) -> None:
    """Record single tool call with timing."""
    safe_args = _sanitize_args(tool_name, args)
    log_event(
        {
            "kind": "tool_call",
            "trace_id": trace_id,
            "tool_name": tool_name,
            "args": safe_args,
            "result_preview": (result_preview or "")[:300],
            "latency_ms": round(latency_ms, 1),
            "success": success,
        }
    )


def log_search_complete(
    trace_id: str,
    turns_used: int,
    files_found: int,
    partial: bool,
    total_latency_ms: float,
) -> None:
    """Record search completion."""
    log_event(
        {
            "kind": "search_complete",
            "trace_id": trace_id,
            "turns_used": turns_used,
            "files_found": files_found,
            "partial": partial,
            "total_latency_ms": round(total_latency_ms, 1),
        }
    )


def log_search_error(trace_id: str, error: str) -> None:
    """Record search error."""
    log_event(
        {
            "kind": "search_error",
            "level": "error",
            "trace_id": trace_id,
            "error": error,
        }
    )


def _sanitize_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive or overly long arguments."""
    safe = dict(args)
    if tool_name == "bash" and "command" in safe:
        cmd = safe["command"]
        safe["command"] = cmd[:197] + "..." if len(cmd) > 200 else cmd
    if tool_name == "grep_search" and "query" in safe:
        q = safe["query"]
        safe["query"] = q[:97] + "..." if len(q) > 100 else q
    return safe
