import glob
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

_LEVEL_RANK: dict[str, int] = {"debug": 10, "info": 20, "warning": 30, "error": 40}


def _normalize_level(value: object, *, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _LEVEL_RANK:
        return text
    if text == "warn":
        return "warning"
    return default


def _level_rank(level: str) -> int:
    return _LEVEL_RANK.get(level, _LEVEL_RANK["info"])


def _normalize_kind(value: object) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text or "unknown"


def _should_log_trace(kind: str, level: str) -> bool:
    include = settings.MCP_TRACE_INCLUDE_KINDS
    if include and kind not in include:
        return False

    exclude = settings.MCP_TRACE_EXCLUDE_KINDS
    if exclude and kind in exclude:
        return False

    min_level = _normalize_level(settings.MCP_LOG_FILE_LEVEL, default="debug")
    return _level_rank(level) >= _level_rank(min_level)


def rotate_trace_if_needed() -> None:
    """Rotate the trace log when it exceeds the configured size limit."""
    try:
        trace_path = settings.TRACE_PATH
        if trace_path.exists() and trace_path.stat().st_size > settings.MAX_TRACE_LOG_SIZE_BYTES:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            stem = trace_path.stem
            suffix = trace_path.suffix
            rotated_path = trace_path.with_name(f"{stem}.{ts}{suffix}")
            trace_path.rename(rotated_path)
            logger.debug("Rotated trace file to %s", rotated_path)

            pattern = f"{glob.escape(stem)}.*{glob.escape(suffix)}"
            rotated_traces = sorted(
                trace_path.parent.glob(pattern),
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
        event: Trace event payload. Enriched with timestamp, trace_id, and level if missing.
    """
    if not settings.MCP_TRACE_LOGGING:
        return

    event = dict(event)
    try:
        kind = _normalize_kind(event.get("kind"))

        # Infer level when not explicitly provided
        if "level" not in event:
            if kind.endswith("error") or kind.endswith("exception"):
                event["level"] = "error"
            elif event.get("success") is False:
                event["level"] = "warning"
            else:
                event["level"] = "debug"
        level = _normalize_level(event.get("level"), default="debug")
        event["level"] = level

        if not _should_log_trace(kind, level):
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
