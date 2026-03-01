import glob
import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from ..config import settings
from .context import get_trace_id, tool_name

logger = logging.getLogger(__name__)

MAX_ROTATED_LOGS = 5
_LOG_LOCK = threading.Lock()

_LEVEL_RANK: dict[str, int] = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}

# Keys whose string values contain sensitive content and must be redacted in safe mode.
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "query",
        "query_preview",
        "edit_snippet",
        "edit_snippet_preview",
        "instruction",
        "arguments",
        "command",
        "result",
        "result_preview",
        "stdout",
        "stderr",
        "traceback",
        "error",
        "detail",
        "message",
        "reason",
        "explanation",
        "recommended_action",
        "payload_preview",
    }
)

# Keys that are never redacted — they carry classification metadata for audit analysis.
_NEVER_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "error_type",
        "error_code",
        "status_code",
    }
)

_SANITIZE_DEPTH_LIMIT = 6
_SANITIZE_LIST_LIMIT = 20


def _make_placeholder(value: str) -> str:
    hex12 = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"[REDACTED len={len(value)} sha256={hex12}]"


def _sanitize_value(key: str, value: Any, depth: int) -> Any:
    if depth > _SANITIZE_DEPTH_LIMIT:
        return "[REDACTED depth_limit]"
    if isinstance(value, dict):
        return _sanitize_event_inner(value, depth + 1)
    if isinstance(value, list):
        is_sensitive = key.lower() in _SENSITIVE_KEYS and key.lower() not in _NEVER_REDACT_KEYS
        result: list[Any] = []
        for item in value[:_SANITIZE_LIST_LIMIT]:
            if isinstance(item, str) and is_sensitive:
                result.append(_make_placeholder(item))
            elif isinstance(item, dict):
                result.append(_sanitize_event_inner(item, depth + 1))
            elif isinstance(item, list):
                result.append(_sanitize_value(key, item, depth + 1))
            else:
                result.append(item)
        if len(value) > _SANITIZE_LIST_LIMIT:
            result.append(f"[REDACTED list_len={len(value)}]")
        return result
    if isinstance(value, str):
        k = key.lower()
        if k in _SENSITIVE_KEYS and k not in _NEVER_REDACT_KEYS:
            return _make_placeholder(value)
    return value


def _sanitize_event_inner(event: dict[str, Any], depth: int) -> dict[str, Any]:
    return {k: _sanitize_value(k, v, depth) for k, v in event.items()}


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    if not settings.MCP_LOG_REDACT:
        return event
    return _sanitize_event_inner(event, depth=0)


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


def _should_log_event(kind: str, level: str) -> bool:
    return True


def redact_value(value: str, max_len: int = 200) -> str:
    if not value:
        return value
    if settings.MCP_LOG_REDACT:
        return _make_placeholder(value)
    # Full mode: truncate for readability but keep content
    if len(value) <= max_len:
        return value
    suffix = f"... [truncated, len={len(value)}]"
    if max_len <= len(suffix):
        return value[:max_len]
    return f"{value[: max_len - len(suffix)]}{suffix}"


def rotate_log_if_needed() -> None:
    try:
        log_path = settings.LOG_PATH
        if log_path.exists() and log_path.stat().st_size > settings.MAX_LOG_SIZE_BYTES:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            stem = log_path.stem
            suffix = log_path.suffix
            rotated_path = log_path.with_name(f"{stem}.{ts}{suffix}")
            log_path.rename(rotated_path)
            logger.debug("Rotated log file to %s", rotated_path)

            pattern = f"{glob.escape(stem)}.*{glob.escape(suffix)}"
            rotated_logs = sorted(log_path.parent.glob(pattern), reverse=True)
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

        kind = _normalize_kind(event.get("kind"))
        level = _normalize_level(event.get("level"), default="info")
        event["level"] = level
        if not _should_log_event(kind, level):
            return

        event = _sanitize_event(event)

        with _LOG_LOCK:
            if settings.LOG_PATH.is_dir():
                logger.warning("Log path is a directory, skipping log write")
                return
            settings.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            try:
                settings.LOG_PATH.parent.chmod(0o700)
            except OSError:
                pass
            rotate_log_if_needed()
            if settings.LOG_PATH.exists():
                try:
                    settings.LOG_PATH.chmod(0o600)
                except OSError:
                    pass
            with open(settings.LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to write event log: %s", exc)


def log_tool_start(tool: str, params: dict[str, Any] | None = None) -> None:
    event: dict[str, Any] = {"kind": "tool_start", "level": "debug", "tool": tool}
    if params:
        event["params_keys"] = list(params.keys())
        event["params_preview"] = {k: f"len={len(str(v))}" for k, v in params.items()}
    log_event(event)


def log_tool_complete(tool: str, latency_ms: float, result_keys: list[str] | None = None) -> None:
    log_event(
        {
            "kind": "tool_complete",
            "level": "info",
            "tool": tool,
            "latency_ms": int(latency_ms),
            "result_keys": result_keys,
        }
    )


def log_tool_error(
    tool: str,
    latency_ms: float,
    error: str,
    error_type: str | None = None,
    *,
    traceback_str: str | None = None,
) -> None:
    log_event(
        {
            "kind": "tool_error",
            "level": "error",
            "tool": tool,
            "latency_ms": int(latency_ms),
            "error": redact_value(error, 500),
            "error_type": error_type or "Exception",
            "traceback": redact_value(traceback_str, 8000) if traceback_str else None,
        }
    )
