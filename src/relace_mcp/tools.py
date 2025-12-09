import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .config import LOG_PATH, MAX_LOG_SIZE_BYTES, RelaceConfig
from .relace_client import RelaceClient

logger = logging.getLogger(__name__)

# 限制檔案大小為 10MB，避免記憶體耗盡
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


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


def _apply_file_logic(
    client: RelaceClient,
    file_path: str,
    edit_snippet: str,
    instruction: str | None,
    base_dir: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """relace_apply_file 的核心邏輯（可獨立測試）。

    Args:
        client: Relace API 客戶端。
        file_path: 要修改的檔案路徑。
        edit_snippet: 要套用的程式碼片段，需使用省略註解格式（例如 `// ... keep existing code ...`）。
        instruction: 可選的自然語言說明。
        base_dir: 基礎目錄限制。
        dry_run: 若為 True，只回傳 preview 不實際寫入。
        stream: 是否要求串流回應；目前僅支援 False。

    Returns:
        包含 merged_code_preview、usage 及修改 metadata 的 dict。
    """
    started_at = datetime.now(UTC)
    trace_id = str(uuid.uuid4())[:8]

    # 輸入驗證
    if not edit_snippet or not edit_snippet.strip():
        raise RuntimeError("edit_snippet cannot be empty")

    try:
        resolved_path = _validate_file_path(file_path, base_dir)

        # 檢查檔案大小
        try:
            file_size = resolved_path.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                raise RuntimeError(
                    f"File too large ({file_size} bytes). Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes"
                )
        except FileNotFoundError as exc:
            raise RuntimeError(f"File not found: {file_path}") from exc

        # 讀取檔案，處理編碼錯誤
        try:
            with open(resolved_path, encoding="utf-8") as f:
                initial_code = f.read()
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"File is not valid UTF-8 encoding: {file_path}. "
                "Only UTF-8 encoded text files are supported."
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"File not found: {file_path}") from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to read file {file_path}: {exc}") from exc

        relace_metadata = {
            "source": "fastmcp",
            "tool": "relace_apply_file",
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

        # 計算 latency
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)

        # dry_run 模式不寫入檔案
        if not dry_run:
            if resolved_path.exists() and not os.access(resolved_path, os.W_OK):
                raise RuntimeError(f"File is not writable: {file_path}")

            try:
                with open(resolved_path, "w", encoding="utf-8") as f:
                    f.write(merged_code)
            except OSError as exc:
                raise RuntimeError(f"Failed to write merged code to {file_path}: {exc}") from exc

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
                "dry_run": dry_run,
            }
        )
        logger.info(
            "[%s] Applied Relace edit to %s (latency=%dms, dry_run=%s)",
            trace_id,
            resolved_path,
            latency_ms,
            dry_run,
        )

        preview = merged_code[:4000]
        return {
            "file_path": str(resolved_path),
            "instruction": instruction,
            "usage": usage,
            "merged_code_preview": preview,
            "dry_run": dry_run,
        }

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


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """向 FastMCP 實例註冊 Relace 相關 tools。"""
    client = RelaceClient(config)

    @mcp.tool
    def relace_apply_file(
        file_path: str,
        edit_snippet: str,
        instruction: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply a Relace Instant Apply diff to a local source file.

        Args:
            file_path: 要修改的檔案路徑（UTF-8）。
            edit_snippet: 要 merge 進檔案的程式碼片段。
            instruction: 可選的自然語言說明，用來消歧義 edit 行為。
            dry_run: 若為 True，只回傳 preview 不實際寫入檔案。

        Returns:
            包含 merged_code_preview、usage 及修改 metadata 的 dict。
        """
        return _apply_file_logic(
            client=client,
            file_path=file_path,
            edit_snippet=edit_snippet,
            instruction=instruction,
            base_dir=config.base_dir,
            dry_run=dry_run,
        )

    _ = relace_apply_file
