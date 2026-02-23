import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...observability import log_event, redact_value

logger = logging.getLogger(__name__)


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
            "instruction": redact_value(instruction, 200) if instruction else None,
            "edit_snippet_preview": redact_value(edit_snippet, 200),
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
            "instruction": redact_value(instruction, 200) if instruction else None,
            "edit_snippet_preview": redact_value(edit_snippet, 200),
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
            "instruction": redact_value(instruction, 200) if instruction else None,
            "edit_snippet_preview": redact_value(edit_snippet or "", 200),
            "error": str(exc),
        }
    )


def log_apply_recoverable_error(
    trace_id: str,
    started_at: datetime,
    file_path: str,
    edit_snippet: str,
    instruction: str | None,
    *,
    error_code: str | None,
    message: str,
) -> None:
    """Log a recoverable apply error returned as a structured result dict.

    Args:
        trace_id: Trace ID.
        started_at: Start time.
        file_path: File path.
        edit_snippet: Edit snippet.
        instruction: Optional instruction.
        error_code: Structured error code (e.g., INVALID_PATH, NEEDS_MORE_CONTEXT).
        message: Error message.
    """
    latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    error_text = f"{error_code}: {message}" if error_code else message
    log_event(
        {
            "kind": "apply_error",
            "level": "error",
            "trace_id": trace_id,
            "started_at": started_at.isoformat(),
            "latency_ms": latency_ms,
            "file_path": file_path,
            "instruction": redact_value(instruction, 200) if instruction else None,
            "edit_snippet_preview": redact_value(edit_snippet or "", 200),
            "error_code": error_code,
            "error": redact_value(error_text, 500),
        }
    )
