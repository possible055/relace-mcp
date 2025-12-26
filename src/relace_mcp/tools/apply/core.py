import difflib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...clients.apply import ApplyLLMClient, ApplyRequest, ApplyResponse
from ...config.settings import EXPERIMENTAL_POST_CHECK
from ...utils import MAX_FILE_SIZE_BYTES, validate_file_path
from . import errors, file_io, snippet
from . import logging as apply_logging
from .exceptions import (
    ApiInvalidResponseError,
    ApplyError,
    FileNotWritableError,
    FileTooLargeError,
)

logger = logging.getLogger(__name__)


@dataclass
class ApplyContext:
    trace_id: str
    started_at: datetime
    file_path: str
    instruction: str | None

    def elapsed_ms(self) -> int:
        return int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)


def _ok_result(
    ctx: ApplyContext,
    path: str,
    message: str,
    diff: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "path": path,
        "trace_id": ctx.trace_id,
        "timing_ms": ctx.elapsed_ms(),
        "diff": diff,
        "message": message,
    }


def _resolve_path(
    file_path: str, base_dir: str | None, ctx: ApplyContext
) -> tuple[Path, bool, int] | dict[str, Any]:
    """Resolve and validate file path, check file status.

    Args:
        file_path: Target file path (absolute or relative).
        base_dir: Base directory restriction. If None, only absolute paths are accepted.
        ctx: Apply context for error reporting.

    Returns:
        On success returns (resolved_path, file_exists, file_size),
        on failure returns error dict.
    """
    # When base_dir is None, require absolute paths (no boundary restriction)
    if base_dir is None:
        if not os.path.isabs(file_path):
            return errors.recoverable_error(
                "INVALID_PATH",
                "Relative paths require RELACE_BASE_DIR to be set. Use absolute path or set RELACE_BASE_DIR.",
                file_path,
                ctx.instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )
        try:
            resolved_path = Path(file_path).resolve()
        except (OSError, ValueError) as e:
            return errors.recoverable_error(
                "INVALID_PATH", str(e), file_path, ctx.instruction, ctx.trace_id, ctx.elapsed_ms()
            )
    else:
        try:
            resolved_path = validate_file_path(file_path, base_dir)
        except RuntimeError as e:
            return errors.recoverable_error(
                "INVALID_PATH", str(e), file_path, ctx.instruction, ctx.trace_id, ctx.elapsed_ms()
            )

    file_exists = resolved_path.exists()
    if file_exists and not resolved_path.is_file():
        return errors.recoverable_error(
            "INVALID_PATH",
            f"Path exists but is not a file: {resolved_path}",
            file_path,
            ctx.instruction,
            ctx.trace_id,
            ctx.elapsed_ms(),
        )
    file_size = resolved_path.stat().st_size if file_exists else 0
    return resolved_path, file_exists, file_size


def _create_new_file(ctx: ApplyContext, resolved_path: Path, edit_snippet: str) -> dict[str, Any]:
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    file_io.atomic_write(resolved_path, edit_snippet, encoding="utf-8")

    apply_logging.log_create_success(ctx.trace_id, resolved_path, edit_snippet, ctx.instruction)
    logger.info("[%s] Created new file %s", ctx.trace_id, resolved_path)

    return _ok_result(
        ctx,
        str(resolved_path),
        f"Created new file ({resolved_path.stat().st_size} bytes)",
        diff=None,
    )


async def _apply_to_existing_file(
    ctx: ApplyContext,
    backend: ApplyLLMClient,
    resolved_path: Path,
    edit_snippet: str,
    file_size: int,
) -> dict[str, Any]:
    concrete = snippet.concrete_lines(edit_snippet)
    if not concrete:
        return errors.recoverable_error(
            "NEEDS_MORE_CONTEXT",
            "edit_snippet lacks sufficient anchor lines. Please add 1-3 lines of real code for positioning.",
            ctx.file_path,
            ctx.instruction,
            ctx.trace_id,
            ctx.elapsed_ms(),
        )

    if file_size > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(file_size, MAX_FILE_SIZE_BYTES)

    # Pre-check file and directory writability BEFORE calling API (avoid wasting API calls)
    if not os.access(resolved_path, os.W_OK):
        raise FileNotWritableError(ctx.file_path)
    if not os.access(resolved_path.parent, os.W_OK):
        raise FileNotWritableError(f"Directory not writable: {resolved_path.parent}")

    initial_code, detected_encoding = file_io.read_text_with_fallback(resolved_path)

    if snippet.should_run_anchor_precheck(edit_snippet, ctx.instruction):
        if not snippet.anchor_precheck(concrete, initial_code):
            return errors.recoverable_error(
                "NEEDS_MORE_CONTEXT",
                "Anchor lines in edit_snippet cannot be located in the file. Ensure you include 1-3 lines of existing code.",
                ctx.file_path,
                ctx.instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )

    metadata = {
        "source": "fastmcp",
        "tool": "fast_apply",
        "file_path": str(resolved_path),
        "trace_id": ctx.trace_id,
    }

    request = ApplyRequest(
        initial_code=initial_code,
        edit_snippet=edit_snippet,
        instruction=ctx.instruction,
        metadata=metadata,
    )
    response: ApplyResponse = await backend.apply(request)

    merged_code = response.merged_code
    usage = response.usage

    if not isinstance(merged_code, str):
        raise ApiInvalidResponseError()

    diff = "".join(
        difflib.unified_diff(
            initial_code.splitlines(keepends=True),
            merged_code.splitlines(keepends=True),
            fromfile="before",
            tofile="after",
        )
    )

    if not diff:
        if snippet.expects_changes(edit_snippet, initial_code):
            logger.warning(
                "[%s] APPLY_NOOP: Expected changes but got no diff for %s",
                ctx.trace_id,
                resolved_path,
            )
            return errors.recoverable_error(
                "APPLY_NOOP",
                "Apply API returned content identical to initial. Add 1-3 anchor lines before/after target.",
                ctx.file_path,
                ctx.instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )

        logger.info("[%s] No changes needed (idempotent) for %s", ctx.trace_id, resolved_path)
        return _ok_result(
            ctx,
            str(resolved_path),
            "No changes needed (already matches)",
            diff=None,
        )

    # EXPERIMENTAL: Post-check validation (disabled by default, enable via RELACE_EXPERIMENTAL_POST_CHECK)
    if EXPERIMENTAL_POST_CHECK:
        post_check_passed, post_check_reason = snippet.post_check_merged_code(
            edit_snippet, merged_code, initial_code
        )
        if not post_check_passed:
            logger.warning(
                "[%s] POST_CHECK_FAILED for %s: %s",
                ctx.trace_id,
                resolved_path,
                post_check_reason,
            )
            return errors.recoverable_error(
                "POST_CHECK_FAILED",
                f"Merged code does not match expected changes: {post_check_reason}",
                ctx.file_path,
                ctx.instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )

    file_io.atomic_write(resolved_path, merged_code, encoding=detected_encoding)

    try:
        written_content, _ = file_io.read_text_with_fallback(resolved_path)
        if written_content != merged_code:
            logger.error(
                "[%s] WRITE_VERIFY_FAILED: Content mismatch after write for %s",
                ctx.trace_id,
                resolved_path,
            )
            return errors.recoverable_error(
                "WRITE_VERIFY_FAILED",
                "File content does not match expected after write. Possible race condition.",
                ctx.file_path,
                ctx.instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )
    except Exception as exc:
        logger.error(
            "[%s] WRITE_VERIFY_FAILED: Cannot verify write for %s: %s",
            ctx.trace_id,
            resolved_path,
            exc,
        )
        return errors.recoverable_error(
            "WRITE_VERIFY_FAILED",
            f"Cannot verify file content after write: {exc}",
            ctx.file_path,
            ctx.instruction,
            ctx.trace_id,
            ctx.elapsed_ms(),
        )

    apply_logging.log_apply_success(
        ctx.trace_id, ctx.started_at, resolved_path, file_size, edit_snippet, ctx.instruction, usage
    )
    logger.info(
        "[%s] Applied edit to %s (latency=%dms)",
        ctx.trace_id,
        resolved_path,
        ctx.elapsed_ms(),
    )

    return _ok_result(
        ctx,
        str(resolved_path),
        "Applied code changes successfully.",
        diff=diff,
    )


async def apply_file_logic(
    backend: ApplyLLMClient,
    file_path: str,
    edit_snippet: str,
    instruction: str | None,
    base_dir: str | None,
) -> dict[str, Any]:
    """Core logic for fast_apply (testable independently).

    Args:
        backend: Apply backend instance.
        file_path: Target file path.
        edit_snippet: Code snippet to apply, using abbreviation comments.
        instruction: Optional natural language instruction forwarded to the apply backend for disambiguation.
        base_dir: Base directory restriction. If None, only absolute paths are accepted.

    Returns:
        A structured dict with status, path, trace_id, timing_ms, diff, and message.
    """
    ctx = ApplyContext(
        trace_id=str(uuid.uuid4())[:8],
        started_at=datetime.now(UTC),
        file_path=file_path,
        instruction=instruction,
    )

    if not edit_snippet or not edit_snippet.strip():
        return errors.recoverable_error(
            "INVALID_INPUT",
            "edit_snippet cannot be empty",
            file_path,
            instruction,
            ctx.trace_id,
            ctx.elapsed_ms(),
        )

    try:
        result = _resolve_path(file_path, base_dir, ctx)
        if isinstance(result, dict):
            return result
        resolved_path, file_exists, file_size = result

        if not file_exists:
            return _create_new_file(ctx, resolved_path, edit_snippet)
        return await _apply_to_existing_file(ctx, backend, resolved_path, edit_snippet, file_size)
    except Exception as exc:
        import openai

        apply_logging.log_apply_error(
            ctx.trace_id, ctx.started_at, file_path, edit_snippet, instruction, exc
        )

        if isinstance(exc, openai.APIError):
            logger.warning(
                "[%s] Apply API error for %s: %s",
                ctx.trace_id,
                file_path,
                exc,
            )
            return errors.openai_error_to_recoverable(
                exc, file_path, instruction, ctx.trace_id, ctx.elapsed_ms()
            )

        if isinstance(exc, ValueError):
            logger.warning(
                "[%s] API response parsing error for %s: %s",
                ctx.trace_id,
                file_path,
                exc,
            )
            return errors.recoverable_error(
                "API_INVALID_RESPONSE",
                str(exc),
                file_path,
                instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )

        if isinstance(exc, ApplyError):
            logger.warning(
                "[%s] Apply error (%s) for %s: %s",
                ctx.trace_id,
                exc.error_code,
                file_path,
                exc.message,
            )
            return errors.recoverable_error(
                exc.error_code, exc.message, file_path, instruction, ctx.trace_id, ctx.elapsed_ms()
            )

        if isinstance(exc, PermissionError):
            logger.warning("[%s] Permission error for %s: %s", ctx.trace_id, file_path, exc)
            return errors.recoverable_error(
                "PERMISSION_ERROR",
                f"Permission denied: {exc}",
                file_path,
                instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )

        if isinstance(exc, OSError):
            errno_info = f"errno={exc.errno}" if exc.errno else ""
            strerror = exc.strerror or str(exc)
            logger.warning("[%s] Filesystem error for %s: %s", ctx.trace_id, file_path, exc)
            return errors.recoverable_error(
                "FS_ERROR",
                f"Filesystem error ({type(exc).__name__}, {errno_info}): {strerror}",
                file_path,
                instruction,
                ctx.trace_id,
                ctx.elapsed_ms(),
            )

        logger.error("[%s] Apply failed for %s: %s", ctx.trace_id, file_path, exc)
        raise
