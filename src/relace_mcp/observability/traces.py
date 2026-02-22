import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from ..config import settings
from .context import get_trace_id

logger = logging.getLogger(__name__)

MAX_ROTATED_TRACES = 5
_TRACE_LOCK = threading.Lock()


def _normalize_kind(value: object) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text or "unknown"


def _should_log_trace(kind: str) -> bool:
    include = settings.MCP_TRACE_INCLUDE_KINDS
    if include and kind not in include:
        return False

    exclude = settings.MCP_TRACE_EXCLUDE_KINDS
    if exclude and kind in exclude:
        return False

    return True


def rotate_trace_if_needed() -> None:
    """Rotate the trace log when it exceeds the configured size limit."""
    try:
        if (
            settings.TRACE_PATH.exists()
            and settings.TRACE_PATH.stat().st_size > settings.MAX_TRACE_LOG_SIZE_BYTES
        ):
            rotated_path = settings.TRACE_PATH.with_suffix(
                f".{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.jsonl"
            )
            settings.TRACE_PATH.rename(rotated_path)
            logger.debug("Rotated trace file to %s", rotated_path)

            rotated_traces = sorted(
                settings.TRACE_PATH.parent.glob("relace.trace.*.jsonl"),
                reverse=True,
            )
            for old_trace in rotated_traces[MAX_ROTATED_TRACES:]:
                old_trace.unlink(missing_ok=True)
                logger.debug("Cleaned up old trace file: %s", old_trace)
    except Exception as exc:
        logger.warning("Failed to rotate trace file: %s", exc)


def log_trace_event(event: dict[str, Any]) -> None:
    """Write a single JSON trace event to the local trace file.

    This is only enabled when MCP_LOGGING=full.

    Args:
        event: Trace event payload. Enriched with timestamp and trace_id if missing.
    """
    if not settings.MCP_TRACE_LOGGING:
        return

    event = dict(event)
    try:
        kind = _normalize_kind(event.get("kind"))
        if not _should_log_trace(kind):
            return

        if "timestamp" not in event:
            event["timestamp"] = datetime.now(UTC).isoformat()
        if "trace_id" not in event:
            event["trace_id"] = get_trace_id()

        with _TRACE_LOCK:
            if settings.TRACE_PATH.is_dir():
                logger.warning("Trace path is a directory, skipping trace write")
                return
            settings.TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
            rotate_trace_if_needed()
            with open(settings.TRACE_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to write trace event: %s", exc)
