import difflib
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..clients import RelaceClient
from ..config import LOG_PATH, MAX_LOG_SIZE_BYTES

logger = logging.getLogger(__name__)

# 限制檔案大小為 10MB，避免記憶體耗盡
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# 優先嘗試的編碼（覆蓋 99% 使用場景）
_PREFERRED_ENCODINGS = ("utf-8", "gbk")


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
    from charset_normalizer import from_bytes

    result = from_bytes(raw)
    best = result.best()
    if best is None or best.coherence < 0.5:
        raise RuntimeError(f"Cannot detect encoding for file: {path}")
    return str(best), best.encoding


def _rotate_log_if_needed() -> None:
    """若 log 檔案超過大小上限，進行 rotation。"""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_SIZE_BYTES:
            rotated_path = LOG_PATH.with_suffix(
                f".{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"
            )
            LOG_PATH.rename(rotated_path)
            logger.info("Rotated log file to %s", rotated_path)
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


def _validate_file_path(file_path: str, base_dir: str) -> Path:
    """驗證並解析檔案路徑，防止路徑遍歷攻擊。

    Args:
        file_path: 要驗證的檔案路徑。
        base_dir: 基礎目錄，限制存取範圍。

    Returns:
        解析後的 Path 物件。

    Raises:
        RuntimeError: 若路徑無效或超出允許範圍。
    """
    if not file_path or not file_path.strip():
        raise RuntimeError("file_path cannot be empty")

    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Invalid file path: {file_path}") from exc

    # 確保檔案在 base_dir 中
    base_resolved = Path(base_dir).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise RuntimeError(
            f"Access denied: {file_path} is outside allowed directory {base_dir}"
        ) from exc

    return resolved


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
    started_at = datetime.now(UTC)
    trace_id = str(uuid.uuid4())[:8]

    if not edit_snippet or not edit_snippet.strip():
        raise RuntimeError("edit_snippet cannot be empty")

    try:
        resolved_path = _validate_file_path(file_path, base_dir)

        # New file: write directly without calling API
        if not resolved_path.exists():
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_path.write_text(edit_snippet, encoding="utf-8")

            _log_event(
                {
                    "kind": "create_success",
                    "level": "info",
                    "trace_id": trace_id,
                    "file_path": str(resolved_path),
                    "file_size_bytes": resolved_path.stat().st_size,
                }
            )
            logger.info("[%s] Created new file %s", trace_id, resolved_path)
            return f"Created {resolved_path} ({resolved_path.stat().st_size} bytes)"

        # Existing file: check size and read
        file_size = resolved_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise RuntimeError(
                f"File too large ({file_size} bytes). Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes"
            )

        initial_code, detected_encoding = _read_text_with_fallback(resolved_path)

        # Call Relace API
        relace_metadata = {
            "source": "fastmcp",
            "tool": "fast_apply",
            "file_path": str(resolved_path),
            "trace_id": trace_id,
        }

        result = client.apply(
            initial_code=initial_code,
            edit_snippet=edit_snippet,
            instruction=instruction,
            relace_metadata=relace_metadata,
            stream=False,
        )

        merged_code = result.get("mergedCode")
        usage = result.get("usage", {})

        if not isinstance(merged_code, str):
            raise RuntimeError("Relace API did not return 'mergedCode'")

        # Generate UDiff for agent verification
        diff = "".join(
            difflib.unified_diff(
                initial_code.splitlines(keepends=True),
                merged_code.splitlines(keepends=True),
                fromfile="before",
                tofile="after",
            )
        )

        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)

        # No changes detected
        if not diff:
            logger.info("[%s] No changes made to %s", trace_id, resolved_path)
            return "No changes made"

        # Write merged code
        if not os.access(resolved_path, os.W_OK):
            raise RuntimeError(f"File is not writable: {file_path}")

        resolved_path.write_text(merged_code, encoding=detected_encoding)

        _log_event(
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
        logger.info(
            "[%s] Applied Relace edit to %s (latency=%dms)",
            trace_id,
            resolved_path,
            latency_ms,
        )

        return f"Applied code changes using Relace API.\n\nChanges made:\n{diff}"

    except Exception as exc:
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        _log_event(
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
        logger.error("[%s] Relace apply failed for %s: %s", trace_id, file_path, exc)
        raise
