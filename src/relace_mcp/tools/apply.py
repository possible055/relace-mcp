import difflib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from charset_normalizer import from_bytes

from ..clients import RelaceClient
from ..config import LOG_PATH, MAX_LOG_SIZE_BYTES
from ..utils import MAX_FILE_SIZE_BYTES, normalize_repo_path, validate_file_path

logger = logging.getLogger(__name__)

# Log rotation：保留的舊 log 數量上限
MAX_ROTATED_LOGS = 5

# 優先嘗試的編碼（覆蓋 99% 使用場景）
_PREFERRED_ENCODINGS = ("utf-8", "gbk")


@dataclass
class ApplyContext:
    trace_id: str
    started_at: datetime
    file_path: str
    instruction: str | None


def _is_truncation_placeholder(line: str) -> bool:
    """判斷是否為截斷用的 placeholder（省略標記）。

    注意：// remove Block 是 directive，不是 placeholder。
    """
    s = line.strip()
    if not s:
        return True

    lower = s.lower()
    return lower.startswith("// ...") or lower.startswith("# ...")


def _concrete_lines(text: str) -> list[str]:
    """回傳非 placeholder 的行（包含 remove directive）。"""
    return [line for line in text.splitlines() if not _is_truncation_placeholder(line)]


def _recoverable_error(error_code: str, message: str, path: str, instruction: str | None) -> str:
    """產生可恢復錯誤的回傳訊息。"""
    return f"{error_code}\n{message}\npath: {path}\ninstruction: {instruction or ''}\n"


def _read_text_with_fallback(path: Path) -> tuple[str, str]:
    """讀取文字檔案，自動偵測編碼。

    優先嘗試 UTF-8 和 GBK（覆蓋絕大多數場景），
    失敗時使用 charset_normalizer 自動偵測。

    Args:
        path: 檔案路徑。

    Returns:
        (內容, 編碼) 元組。

    Raises:
        RuntimeError: 若無法偵測編碼或檔案非文字檔。
    """
    raw = path.read_bytes()

    # 優先嘗試常用編碼（快速且準確）
    for enc in _PREFERRED_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback：自動偵測
    result = from_bytes(raw)
    best = result.best()
    if best is None or best.coherence < 0.5:
        raise RuntimeError(f"Cannot detect encoding for file: {path}")
    return str(best), best.encoding


def _rotate_log_if_needed() -> None:
    """若 log 檔案超過大小上限，進行 rotation 並清理舊檔案。"""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_SIZE_BYTES:
            rotated_path = LOG_PATH.with_suffix(
                f".{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"
            )
            LOG_PATH.rename(rotated_path)
            logger.info("Rotated log file to %s", rotated_path)

            # 清理超過上限的舊 log 檔案
            rotated_logs = sorted(LOG_PATH.parent.glob("relace_apply.*.log"), reverse=True)
            for old_log in rotated_logs[MAX_ROTATED_LOGS:]:
                old_log.unlink(missing_ok=True)
                logger.debug("Cleaned up old log file: %s", old_log)
    except Exception as exc:
        logger.warning("Failed to rotate log file: %s", exc)


def _log_event(event: dict[str, Any]) -> None:
    """將單筆 JSON event 寫入本地 log，失敗時不影響主流程。"""
    try:
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(UTC).isoformat()
        if "trace_id" not in event:
            event["trace_id"] = str(uuid.uuid4())[:8]
        if "level" not in event:
            event["level"] = "info" if event.get("kind", "").endswith("success") else "error"

        if LOG_PATH.is_dir():
            logger.warning("Log path is a directory, skipping log write: %s", LOG_PATH)
            return
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        _rotate_log_if_needed()

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write Relace log: %s", exc)


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
        return _recoverable_error("INVALID_PATH", str(e), file_path, ctx.instruction)

    # 注意：exists() 和 stat() 可能拋出 OSError（例如 PermissionError）
    # 這些異常應由調用者的 try-except 捕捉以確保正確記錄
    file_exists = resolved_path.exists()
    if file_exists and not resolved_path.is_file():
        return _recoverable_error(
            "INVALID_PATH",
            f"Path exists but is not a file: {resolved_path}",
            file_path,
            ctx.instruction,
        )
    file_size = resolved_path.stat().st_size if file_exists else 0
    return resolved_path, file_exists, file_size


def _log_create_success(ctx: ApplyContext, resolved_path: Path, edit_snippet: str) -> None:
    """記錄新檔案創建成功。"""
    _log_event(
        {
            "kind": "create_success",
            "level": "info",
            "trace_id": ctx.trace_id,
            "file_path": str(resolved_path),
            "file_size_bytes": resolved_path.stat().st_size,
            "instruction": ctx.instruction,
            "edit_snippet_preview": edit_snippet[:200],
        }
    )


def _log_apply_success(
    ctx: ApplyContext, resolved_path: Path, file_size: int, edit_snippet: str, usage: dict[str, Any]
) -> None:
    """記錄編輯套用成功。"""
    latency_ms = int((datetime.now(UTC) - ctx.started_at).total_seconds() * 1000)
    _log_event(
        {
            "kind": "apply_success",
            "level": "info",
            "trace_id": ctx.trace_id,
            "started_at": ctx.started_at.isoformat(),
            "latency_ms": latency_ms,
            "file_path": str(resolved_path),
            "file_size_bytes": file_size,
            "instruction": ctx.instruction,
            "edit_snippet_preview": edit_snippet[:200],
            "usage": usage,
        }
    )


def _log_apply_error(ctx: ApplyContext, edit_snippet: str, exc: Exception) -> None:
    """記錄錯誤（含 latency）。"""
    latency_ms = int((datetime.now(UTC) - ctx.started_at).total_seconds() * 1000)
    _log_event(
        {
            "kind": "apply_error",
            "level": "error",
            "trace_id": ctx.trace_id,
            "started_at": ctx.started_at.isoformat(),
            "latency_ms": latency_ms,
            "file_path": ctx.file_path,
            "instruction": ctx.instruction,
            "edit_snippet_preview": (edit_snippet or "")[:200],
            "error": str(exc),
        }
    )


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
    resolved_path.write_text(edit_snippet, encoding="utf-8")

    _log_create_success(ctx, resolved_path, edit_snippet)
    logger.info("[%s] Created new file %s", ctx.trace_id, resolved_path)
    return f"Created {resolved_path} ({resolved_path.stat().st_size} bytes)"


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
        RuntimeError: 檔案過大、API 失敗或檔案不可寫入。
    """
    concrete = _concrete_lines(edit_snippet)
    if not concrete:
        return _recoverable_error(
            "NEEDS_MORE_CONTEXT",
            "edit_snippet 沒有足夠的 anchor lines。請加入 1-3 行真實程式碼作為定位。",
            ctx.file_path,
            ctx.instruction,
        )

    if file_size > MAX_FILE_SIZE_BYTES:
        raise RuntimeError(
            f"File too large ({file_size} bytes). Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes"
        )

    initial_code, detected_encoding = _read_text_with_fallback(resolved_path)

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
        raise RuntimeError("Relace API did not return 'mergedCode'")

    diff = "".join(
        difflib.unified_diff(
            initial_code.splitlines(keepends=True),
            merged_code.splitlines(keepends=True),
            fromfile="before",
            tofile="after",
        )
    )

    if not diff:
        logger.info("[%s] No changes made to %s", ctx.trace_id, resolved_path)
        return "No changes made"

    if not os.access(resolved_path, os.W_OK):
        raise RuntimeError(f"File is not writable: {ctx.file_path}")

    resolved_path.write_text(merged_code, encoding=detected_encoding)

    _log_apply_success(ctx, resolved_path, file_size, edit_snippet, usage)
    logger.info(
        "[%s] Applied Relace edit to %s (latency=%dms)",
        ctx.trace_id,
        resolved_path,
        int((datetime.now(UTC) - ctx.started_at).total_seconds() * 1000),
    )

    return f"Applied code changes using Relace API.\n\nChanges made:\n{diff}"


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
        return _recoverable_error(
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
        _log_apply_error(ctx, edit_snippet, exc)
        logger.error("[%s] Relace apply failed for %s: %s", ctx.trace_id, file_path, exc)
        raise
