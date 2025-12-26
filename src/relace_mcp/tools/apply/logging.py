import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...config import settings

logger = logging.getLogger(__name__)

# Log rotation: maximum number of old logs to keep
MAX_ROTATED_LOGS = 5


def rotate_log_if_needed() -> None:
    """Rotate log file if it exceeds size limit and clean up old files."""
    try:
        if (
            settings.LOG_PATH.exists()
            and settings.LOG_PATH.stat().st_size > settings.MAX_LOG_SIZE_BYTES
        ):
            rotated_path = settings.LOG_PATH.with_suffix(
                f".{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"
            )
            settings.LOG_PATH.rename(rotated_path)
            logger.info("Rotated log file to %s", rotated_path)

            # Clean up old log files exceeding limit
            rotated_logs = sorted(settings.LOG_PATH.parent.glob("relace.*.log"), reverse=True)
            for old_log in rotated_logs[MAX_ROTATED_LOGS:]:
                old_log.unlink(missing_ok=True)
                logger.debug("Cleaned up old log file: %s", old_log)
    except Exception as exc:
        logger.warning("Failed to rotate log file: %s", exc)


def log_event(event: dict[str, Any]) -> None:
    """Write a single JSON event to local log, failures don't affect main flow.

    Args:
        event: Event data to log.
    """
    if not settings.RELACE_LOGGING:
        return

    try:
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(UTC).isoformat()
        if "trace_id" not in event:
            event["trace_id"] = str(uuid.uuid4())[:8]
        if "level" not in event:
            kind = str(event.get("kind", "")).lower()
            event["level"] = "error" if kind.endswith("error") else "info"

        if settings.LOG_PATH.is_dir():
            logger.warning("Log path is a directory, skipping log write: %s", settings.LOG_PATH)
            return
        settings.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        rotate_log_if_needed()

        with open(settings.LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write Relace log: %s", exc)


def log_create_success(
    trace_id: str, resolved_path: Path, edit_snippet: str, instruction: str | None
) -> None:
    """Log successful new file creation.

    Args:
        trace_id: Trace ID.
        resolved_path: Resolved file path.
        edit_snippet: Edit snippet.
        instruction: Optional instruction.
    """
    log_event(
        {
            "kind": "create_success",
            "level": "info",
            "trace_id": trace_id,
            "file_path": str(resolved_path),
            "file_size_bytes": resolved_path.stat().st_size,
            "instruction": instruction,
            "edit_snippet_preview": edit_snippet[:200],
        }
    )


def log_apply_success(
    trace_id: str,
    started_at: datetime,
    resolved_path: Path,
    file_size: int,
    edit_snippet: str,
    instruction: str | None,
    usage: dict[str, Any],
) -> None:
    """Log successful edit application.

    Args:
        trace_id: Trace ID.
        started_at: Start time.
        resolved_path: Resolved file path.
        file_size: File size.
        edit_snippet: Edit snippet.
        instruction: Optional instruction.
        usage: API usage information.
    """
    latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    log_event(
        {
            "kind": "apply_success",
            "level": "info",
            "trace_id": trace_id,
            "started_at": started_at.isoformat(),
            "latency_ms": latency_ms,
            "file_path": str(resolved_path),
            "file_size_bytes": file_size,
            "instruction": instruction,
            "edit_snippet_preview": edit_snippet[:200],
            "usage": usage,
        }
    )


def log_apply_error(
    trace_id: str,
    started_at: datetime,
    file_path: str,
    edit_snippet: str,
    instruction: str | None,
    exc: Exception,
) -> None:
    """Log error (with latency).

    Args:
        trace_id: Trace ID.
        started_at: Start time.
        file_path: File path.
        edit_snippet: Edit snippet.
        instruction: Optional instruction.
        exc: Exception.
    """
    latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    log_event(
        {
            "kind": "apply_error",
            "level": "error",
            "trace_id": trace_id,
            "started_at": started_at.isoformat(),
            "latency_ms": latency_ms,
            "file_path": file_path,
            "instruction": instruction,
            "edit_snippet_preview": (edit_snippet or "")[:200],
            "error": str(exc),
        }
    )
