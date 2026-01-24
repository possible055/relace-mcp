import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from ..config import settings
from .context import get_trace_id, tool_name
from .settings import MCP_LOG_REDACT

logger = logging.getLogger(__name__)

MAX_ROTATED_LOGS = 5
_LOG_LOCK = threading.Lock()


def redact_value(value: str, max_len: int = 200) -> str:
    if not value:
        return value
    if not MCP_LOG_REDACT:
        return value[:max_len] if len(value) > max_len else value
    if len(value) <= max_len:
        return value
    suffix = f"... [truncated, len={len(value)}]"
    if max_len <= len(suffix):
        return value[:max_len]
    return f"{value[: max_len - len(suffix)]}{suffix}"


def rotate_log_if_needed() -> None:
    try:
        if (
            settings.LOG_PATH.exists()
            and settings.LOG_PATH.stat().st_size > settings.MAX_LOG_SIZE_BYTES
        ):
            rotated_path = settings.LOG_PATH.with_suffix(
                f".{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"
            )
            settings.LOG_PATH.rename(rotated_path)
            logger.debug("Rotated log file to %s", rotated_path)

            rotated_logs = sorted(settings.LOG_PATH.parent.glob("relace.*.log"), reverse=True)
            for old_log in rotated_logs[MAX_ROTATED_LOGS:]:
                old_log.unlink(missing_ok=True)
                logger.debug("Cleaned up old log file: %s", old_log)
    except Exception as exc:
        logger.warning("Failed to rotate log file: %s", exc)


def log_event(event: dict[str, Any]) -> None:
    """Write a single JSON event to local log file.

    Args:
        event: Event data to log. Will be enriched with timestamp, trace_id, tool, level.
    """
    if not settings.MCP_LOGGING:
        return

    event = dict(event)
    try:
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(UTC).isoformat()
        if "trace_id" not in event:
            event["trace_id"] = get_trace_id()
        if "tool" not in event:
            current_tool = tool_name.get()
            if current_tool:
                event["tool"] = current_tool
        if "level" not in event:
            kind = str(event.get("kind", "")).lower()
            event["level"] = "error" if kind.endswith("error") else "info"

        with _LOG_LOCK:
            if settings.LOG_PATH.is_dir():
                logger.warning("Log path is a directory, skipping log write")
                return
            settings.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            rotate_log_if_needed()
            with open(settings.LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write event log: %s", exc)


def log_tool_start(tool: str, params: dict[str, Any] | None = None) -> None:
    event: dict[str, Any] = {"kind": "tool_start", "tool": tool}
    if params:
        event["params_keys"] = list(params.keys())
        event["params_preview"] = {k: f"len={len(str(v))}" for k, v in params.items()}
    log_event(event)


def log_tool_complete(tool: str, latency_ms: float, result_keys: list[str] | None = None) -> None:
    log_event(
        {
            "kind": "tool_complete",
            "tool": tool,
            "latency_ms": int(latency_ms),
            "result_keys": result_keys,
        }
    )


def log_tool_error(tool: str, latency_ms: float, error: str, error_type: str | None = None) -> None:
    log_event(
        {
            "kind": "tool_error",
            "tool": tool,
            "latency_ms": int(latency_ms),
            "error": redact_value(error, 500),
            "error_type": error_type or "Exception",
        }
    )
