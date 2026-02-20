# pyright: reportUnusedFunction=false
import logging
from pathlib import Path, PurePosixPath, PureWindowsPath

from ...encoding import decode_text_best_effort, get_project_encoding
from ._sync_constants import SYNC_MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)


def _read_file_content(base_dir: str, rel_path: str) -> bytes | None:
    """Read file content as bytes.

    Returns:
        File content, or None if read fails or path escapes base_dir.
    """
    try:
        base_path = Path(base_dir).resolve()
        if PurePosixPath(rel_path).is_absolute() or PureWindowsPath(rel_path).is_absolute():
            logger.warning("Blocked absolute path read: %s", rel_path)
            return None
        candidate = base_path / rel_path
        if candidate.is_symlink():
            logger.warning("Blocked symlink read: %s", rel_path)
            return None
        try:
            file_path = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            logger.debug("Failed to resolve %s: %s", rel_path, exc)
            return None
        if not file_path.is_relative_to(base_path):
            logger.warning("Blocked path traversal attempt: %s", rel_path)
            return None
        if not file_path.is_file():
            return None
        if file_path.stat().st_size > SYNC_MAX_FILE_SIZE_BYTES:
            return None
        return file_path.read_bytes()
    except (OSError, RuntimeError) as exc:
        logger.debug("Failed to read %s: %s", rel_path, exc)
        return None


def _decode_file_content(content: bytes, *, path: Path | None = None) -> str | None:
    """Decode file content with project encoding support.

    Args:
        content: Raw file bytes.

    Returns:
        Decoded string, or None if decoding fails (binary file).
    """
    project_enc = get_project_encoding()
    return decode_text_best_effort(
        content,
        path=path,
        preferred_encoding=project_enc,
        errors="replace",
    )
