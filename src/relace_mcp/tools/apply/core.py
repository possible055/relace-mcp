import difflib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ...clients import RelaceClient
from ...utils import MAX_FILE_SIZE_BYTES, normalize_repo_path, validate_file_path
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


def _resolve_path(file_path: str, base_dir: str, ctx: ApplyContext) -> tuple[Path, bool, int] | str:
    """解析並驗證檔案路徑，檢查檔案狀態。

    Args:
        file_path: 目標檔案路徑。
        base_dir: 基礎目錄限制。
        ctx: Apply context。

    Returns:
        成功時返回 (resolved_path, file_exists, file_size)，
        失敗時返回錯誤訊息字串。

    Raises:
        OSError: 文件系統操作失敗（exists/stat）時拋出，由調用者捕捉並記錄。
    """
    try:
        normalized = normalize_repo_path(file_path, base_dir)
        resolved_path = validate_file_path(normalized, base_dir)
    except RuntimeError as e:
        return errors.recoverable_error("INVALID_PATH", str(e), file_path, ctx.instruction)

    # 注意：exists() 和 stat() 可能拋出 OSError（例如 PermissionError）
    # 這些異常應由調用者的 try-except 捕捉以確保正確記錄
    file_exists = resolved_path.exists()
    if file_exists and not resolved_path.is_file():
        return errors.recoverable_error(
            "INVALID_PATH",
            f"Path exists but is not a file: {resolved_path}",
            file_path,
            ctx.instruction,
        )
    file_size = resolved_path.stat().st_size if file_exists else 0
    return resolved_path, file_exists, file_size


def _create_new_file(ctx: ApplyContext, resolved_path: Path, edit_snippet: str) -> str:
    """創建新檔案並寫入內容。

    Args:
        ctx: Apply context。
        resolved_path: 解析後的檔案路徑。
        edit_snippet: 要寫入的內容。

    Returns:
        成功訊息。
    """
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    file_io.atomic_write(resolved_path, edit_snippet, encoding="utf-8")

    apply_logging.log_create_success(ctx.trace_id, resolved_path, edit_snippet, ctx.instruction)
    logger.info("[%s] Created new file %s", ctx.trace_id, resolved_path)
    return (
        f"OK\n"
        f"path: {resolved_path}\n"
        f"trace_id: {ctx.trace_id}\n"
        f"Created new file ({resolved_path.stat().st_size} bytes)"
    )


def _apply_to_existing_file(
    ctx: ApplyContext,
    client: RelaceClient,
    resolved_path: Path,
    edit_snippet: str,
    file_size: int,
) -> str:
    """應用編輯到現有檔案。

    Args:
        ctx: Apply context。
        client: Relace API client。
        resolved_path: 解析後的檔案路徑。
        edit_snippet: 要套用的程式碼變更片段。
        file_size: 檔案大小。

    Returns:
        成功訊息（含 diff）。

    Raises:
        ApplyError: 可預期的套用失敗（例如檔案過大、編碼偵測失敗、回應格式異常、檔案不可寫入）。
        OSError: 檔案系統操作失敗（由外層捕捉並轉為可恢復錯誤）。
    """
    concrete = snippet.concrete_lines(edit_snippet)
    if not concrete:
        return errors.recoverable_error(
            "NEEDS_MORE_CONTEXT",
            "edit_snippet 沒有足夠的 anchor lines。請加入 1-3 行真實程式碼作為定位。",
            ctx.file_path,
            ctx.instruction,
        )

    if file_size > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(file_size, MAX_FILE_SIZE_BYTES)

    initial_code, detected_encoding = file_io.read_text_with_fallback(resolved_path)

    # Anchor precheck：只在特定情況下執行（避免阻擋合法使用場景）
    if snippet.should_run_anchor_precheck(edit_snippet, ctx.instruction):
        if not snippet.anchor_precheck(concrete, initial_code):
            return errors.recoverable_error(
                "NEEDS_MORE_CONTEXT",
                "edit_snippet 中的 anchor lines 無法在檔案中定位。請確保包含 1-3 行真實存在的程式碼。",
                ctx.file_path,
                ctx.instruction,
            )

    relace_metadata = {
        "source": "fastmcp",
        "tool": "fast_apply",
        "file_path": str(resolved_path),
        "trace_id": ctx.trace_id,
    }

    result = client.apply(
        initial_code=initial_code,
        edit_snippet=edit_snippet,
        instruction=ctx.instruction,
        relace_metadata=relace_metadata,
    )

    merged_code = result.get("mergedCode")
    usage = result.get("usage", {})

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
        # 區分「本來就相同（idempotent）」和「apply 失敗（should-have-changed）」
        if snippet.expects_changes(edit_snippet, initial_code):
            # 預期會產生變更但實際沒有，這是 apply 失敗（需要補救）
            logger.warning(
                "[%s] APPLY_NOOP: Expected changes but got no diff for %s",
                ctx.trace_id,
                resolved_path,
            )
            return errors.recoverable_error(
                "APPLY_NOOP",
                "Relace returned mergedCode identical to initial. Add 1-3 anchor lines before/after target.",
                ctx.file_path,
                ctx.instruction,
            )

        # 真正的 idempotent 情況（編輯內容本來就已存在）
        logger.info("[%s] No changes needed (idempotent) for %s", ctx.trace_id, resolved_path)
        return (
            f"OK\n"
            f"path: {resolved_path}\n"
            f"trace_id: {ctx.trace_id}\n"
            f"No changes needed (already matches)"
        )

    if not os.access(resolved_path, os.W_OK):
        raise FileNotWritableError(ctx.file_path)

    # 備份檔案（如果啟用）
    file_io.backup_file(resolved_path, ctx.trace_id)

    file_io.atomic_write(resolved_path, merged_code, encoding=detected_encoding)

    # 寫入後驗證：立即讀回比對
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
        )

    apply_logging.log_apply_success(
        ctx.trace_id, ctx.started_at, resolved_path, file_size, edit_snippet, ctx.instruction, usage
    )
    logger.info(
        "[%s] Applied Relace edit to %s (latency=%dms)",
        ctx.trace_id,
        resolved_path,
        int((datetime.now(UTC) - ctx.started_at).total_seconds() * 1000),
    )

    return (
        f"OK\n"
        f"path: {resolved_path}\n"
        f"trace_id: {ctx.trace_id}\n"
        f"Applied code changes using Relace API.\n\n"
        f"Changes made:\n{diff}"
    )


def apply_file_logic(
    client: RelaceClient,
    file_path: str,
    edit_snippet: str,
    instruction: str | None,
    base_dir: str,
) -> str:
    """Core logic for fast_apply (testable independently).

    Args:
        client: Relace API client.
        file_path: Target file path.
        edit_snippet: Code snippet to apply, using abbreviation comments.
        instruction: Optional natural language instruction.
        base_dir: Base directory restriction.

    Returns:
        A message with UDiff showing changes made.
    """
    ctx = ApplyContext(
        trace_id=str(uuid.uuid4())[:8],
        started_at=datetime.now(UTC),
        file_path=file_path,
        instruction=instruction,
    )

    if not edit_snippet or not edit_snippet.strip():
        return errors.recoverable_error(
            "INVALID_INPUT", "edit_snippet cannot be empty", file_path, instruction
        )

    try:
        result = _resolve_path(file_path, base_dir, ctx)
        if isinstance(result, str):
            return result
        resolved_path, file_exists, file_size = result

        if not file_exists:
            return _create_new_file(ctx, resolved_path, edit_snippet)
        return _apply_to_existing_file(ctx, client, resolved_path, edit_snippet, file_size)
    except Exception as exc:
        # 捕捉特定 API/網路錯誤並轉為可恢復訊息
        from ...clients.exceptions import RelaceAPIError, RelaceNetworkError, RelaceTimeoutError

        apply_logging.log_apply_error(
            ctx.trace_id, ctx.started_at, file_path, edit_snippet, instruction, exc
        )

        if isinstance(exc, (RelaceAPIError, RelaceNetworkError, RelaceTimeoutError)):
            logger.warning(
                "[%s] Relace apply recoverable error for %s: %s",
                ctx.trace_id,
                file_path,
                exc,
            )
            return errors.api_error_to_recoverable(exc, file_path, instruction)

        # 自定義 ApplyError：直接映射 error_code
        if isinstance(exc, ApplyError):
            logger.warning(
                "[%s] Apply error (%s) for %s: %s",
                ctx.trace_id,
                exc.error_code,
                file_path,
                exc.message,
            )
            return errors.recoverable_error(exc.error_code, exc.message, file_path, instruction)

        # 檔案系統/環境錯誤：盡量轉為可恢復錯誤，避免 MCP tool 直接 isError=True
        if isinstance(exc, PermissionError):
            logger.warning("[%s] Permission error for %s: %s", ctx.trace_id, file_path, exc)
            return errors.recoverable_error(
                "PERMISSION_ERROR",
                f"Permission denied: {exc}",
                file_path,
                instruction,
            )

        if isinstance(exc, OSError):
            # 帶上 errno/strerror 讓 agent 更好判斷是否值得重試
            errno_info = f"errno={exc.errno}" if exc.errno else ""
            strerror = exc.strerror or str(exc)
            logger.warning("[%s] Filesystem error for %s: %s", ctx.trace_id, file_path, exc)
            return errors.recoverable_error(
                "FS_ERROR",
                f"Filesystem error ({type(exc).__name__}, {errno_info}): {strerror}",
                file_path,
                instruction,
            )

        # 其他未預期錯誤仍然 raise（例如程式邏輯錯誤）
        logger.error("[%s] Relace apply failed for %s: %s", ctx.trace_id, file_path, exc)
        raise
