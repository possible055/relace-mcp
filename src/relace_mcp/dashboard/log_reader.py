import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config.settings import LOG_PATH

APPLY_KINDS = frozenset({"create_success", "apply_success", "apply_error"})
SEARCH_KINDS = frozenset(
    {"search_start", "search_turn", "tool_call", "search_complete", "search_error"}
)
INSIGHTS_KINDS = frozenset({"search_start", "search_turn", "tool_call"})
ALL_KINDS = APPLY_KINDS | SEARCH_KINDS


def get_log_path() -> Path:
    return LOG_PATH


def parse_log_event(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        event = json.loads(line)
        if isinstance(event, dict) and "kind" in event:
            return event
        return None
    except json.JSONDecodeError:
        return None


def get_event_timestamp(event: dict[str, Any]) -> datetime | None:
    ts = event.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def filter_event(
    event: dict[str, Any],
    *,
    enabled_kinds: set[str] | None = None,
    ignored_tools: set[str] | None = None,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
) -> bool:
    kind = event.get("kind", "")

    if enabled_kinds is not None and kind not in enabled_kinds:
        return False

    if ignored_tools and kind == "tool_call":
        tool_name = event.get("tool_name", "")
        if tool_name in ignored_tools:
            return False

    if time_start or time_end:
        ts = get_event_timestamp(event)
        if ts:
            if time_start and ts < time_start:
                return False
            if time_end and ts > time_end:
                return False

    return True


def read_log_events(
    *,
    enabled_kinds: set[str] | None = None,
    ignored_tools: set[str] | None = None,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
    max_events: int = 1000,
) -> list[dict[str, Any]]:
    log_path = get_log_path()
    if not log_path.exists():
        return []

    events = []
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            event = parse_log_event(line)
            if event and filter_event(
                event,
                enabled_kinds=enabled_kinds,
                ignored_tools=ignored_tools,
                time_start=time_start,
                time_end=time_end,
            ):
                events.append(event)
                if len(events) >= max_events:
                    break
    return events


def tail_log(
    callback: Callable[[dict[str, Any]], None],
    *,
    enabled_kinds: set[str] | None = None,
    ignored_tools: set[str] | None = None,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
) -> None:
    import time

    log_path = get_log_path()
    if not log_path.exists():
        return

    with open(log_path, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)  # Go to end of file
        while True:
            line = f.readline()
            if line:
                event = parse_log_event(line)
                if event and filter_event(
                    event,
                    enabled_kinds=enabled_kinds,
                    ignored_tools=ignored_tools,
                    time_start=time_start,
                    time_end=time_end,
                ):
                    callback(event)
            else:
                time.sleep(0.1)


def compute_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    apply_success = 0
    apply_error = 0
    search_complete = 0
    search_error = 0
    latencies: list[float] = []

    for event in events:
        kind = event.get("kind", "")
        if kind in ("apply_success", "create_success"):
            apply_success += 1
        elif kind == "apply_error":
            apply_error += 1
        elif kind == "search_complete":
            search_complete += 1
        elif kind == "search_error":
            search_error += 1

        if "latency_ms" in event:
            latencies.append(event["latency_ms"])

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "total": len(events),
        "apply_success": apply_success,
        "apply_error": apply_error,
        "search_complete": search_complete,
        "search_error": search_error,
        "latencies": latencies,
        "avg_latency_ms": avg_latency,
    }


def get_time_presets() -> dict[str, tuple[datetime, datetime]]:
    now = datetime.now(UTC)
    return {
        "1h": (now - timedelta(hours=1), now),
        "6h": (now - timedelta(hours=6), now),
        "24h": (now - timedelta(hours=24), now),
        "All": (datetime.min.replace(tzinfo=UTC), now),
    }


def get_aggregated_tool_stats(
    events: list[dict[str, Any]], max_tool_calls: int = 100, include_failed: bool = True
) -> list[dict[str, Any]]:
    """Aggregate tool calls by turn globally, limited to last N tool calls."""
    # First, filter to just tool_call events
    if include_failed:
        tool_calls = [e for e in events if e.get("kind") == "tool_call"]
    else:
        tool_calls = [e for e in events if e.get("kind") == "tool_call" and e.get("success", True)]

    # Limit to last N tool calls
    if len(tool_calls) > max_tool_calls:
        tool_calls = tool_calls[-max_tool_calls:]

    # Map: turn -> {tool_name: count}
    aggregated: dict[int, dict[str, int]] = {}

    for event in tool_calls:
        turn = event.get("turn", 0)
        tool_name = event.get("tool_name", "unknown")

        if turn not in aggregated:
            aggregated[turn] = {}

        aggregated[turn][tool_name] = aggregated[turn].get(tool_name, 0) + 1

    # Convert to a sorted list of turns
    result = []
    for turn_num in sorted(aggregated.keys()):
        result.append({"turn": turn_num, "tools": aggregated[turn_num]})

    return result
