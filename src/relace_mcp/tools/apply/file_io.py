import logging
import os
import shutil
from pathlib import Path

from charset_normalizer import from_bytes

from ...config import BACKUP_DIR, RELACE_BACKUP_ENABLED
from .exceptions import EncodingDetectionError

logger = logging.getLogger(__name__)

# 優先嘗試的編碼（覆蓋 99% 使用場景）
PREFERRED_ENCODINGS = ("utf-8", "gbk")


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    """讀取文字檔案，自動偵測編碼。

    優先嘗試 UTF-8 和 GBK（覆蓋絕大多數場景），
    失敗時使用 charset_normalizer 自動偵測。

    Args:
        path: 檔案路徑。

    Returns:
        (內容, 編碼) 元組。

    Raises:
        EncodingDetectionError: 若無法偵測編碼或檔案非文字檔。
    """
    raw = path.read_bytes()

    # 優先嘗試常用編碼（快速且準確）
    for enc in PREFERRED_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback：自動偵測
    result = from_bytes(raw)
    best = result.best()
    if best is None or best.coherence < 0.5:
        raise EncodingDetectionError(str(path))
    return str(best), best.encoding


def atomic_write(path: Path, content: str, encoding: str) -> None:
    """原子寫入檔案（使用臨時檔案 + os.replace）。

    原子寫入可避免寫入過程中被中斷導致檔案損壞。

    Args:
        path: 目標檔案路徑。
        content: 要寫入的內容。
        encoding: 編碼。

    Raises:
        OSError: 寫入失敗時拋出。
    """
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temp_path.write_text(content, encoding=encoding)
        # os.replace 在 POSIX 系統上是原子操作
        os.replace(temp_path, path)
    except Exception:
        # 清理臨時檔案
        temp_path.unlink(missing_ok=True)
        raise


def backup_file(path: Path, trace_id: str) -> Path | None:
    """備份檔案到備份目錄（如果啟用備份機制）。

    Args:
        path: 要備份的檔案路徑。
        trace_id: 追蹤 ID，用於組織備份。

    Returns:
        備份檔案路徑，若未啟用或失敗則返回 None。
    """
    if not RELACE_BACKUP_ENABLED:
        return None

    if not path.exists():
        return None

    try:
        # 建立 trace_id 專屬的備份目錄
        backup_trace_dir = BACKUP_DIR / trace_id
        backup_trace_dir.mkdir(parents=True, exist_ok=True)

        # 使用原始檔名作為備份檔名
        backup_path = backup_trace_dir / path.name
        shutil.copy2(path, backup_path)

        logger.info("[%s] Backed up %s to %s", trace_id, path, backup_path)
        return backup_path
    except Exception as exc:
        logger.warning("[%s] Failed to backup %s: %s", trace_id, path, exc)
        return None
