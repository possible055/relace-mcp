import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...config import LOG_PATH, MAX_LOG_SIZE_BYTES

logger = logging.getLogger(__name__)

# Log rotation：保留的舊 log 數量上限
MAX_ROTATED_LOGS = 5


def rotate_log_if_needed() -> None:
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


def log_event(event: dict[str, Any]) -> None:
    """將單筆 JSON event 寫入本地 log，失敗時不影響主流程。

    Args:
        event: 要記錄的事件資料。
    """
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

        rotate_log_if_needed()

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write Relace log: %s", exc)


def log_create_success(
    trace_id: str, resolved_path: Path, edit_snippet: str, instruction: str | None
) -> None:
    """記錄新檔案創建成功。

    Args:
        trace_id: 追蹤 ID。
        resolved_path: 解析後的檔案路徑。
        edit_snippet: 編輯片段。
        instruction: 可選的 instruction。
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
    """記錄編輯套用成功。

    Args:
        trace_id: 追蹤 ID。
        started_at: 開始時間。
        resolved_path: 解析後的檔案路徑。
        file_size: 檔案大小。
        edit_snippet: 編輯片段。
        instruction: 可選的 instruction。
        usage: API 使用資訊。
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
    """記錄錯誤（含 latency）。

    Args:
        trace_id: 追蹤 ID。
        started_at: 開始時間。
        file_path: 檔案路徑。
        edit_snippet: 編輯片段。
        instruction: 可選的 instruction。
        exc: 例外。
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
