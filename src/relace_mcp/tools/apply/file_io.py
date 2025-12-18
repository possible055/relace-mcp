import logging
import os
import uuid
from pathlib import Path

from charset_normalizer import from_bytes

from .exceptions import EncodingDetectionError

logger = logging.getLogger(__name__)

# Preferred encodings to try first (covers 99% of use cases)
PREFERRED_ENCODINGS = ("utf-8", "gbk")


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    """Read text file with automatic encoding detection.

    Tries UTF-8 and GBK first (covers most scenarios),
    falls back to charset_normalizer auto-detection on failure.

    Args:
        path: File path.

    Returns:
        (content, encoding) tuple.

    Raises:
        EncodingDetectionError: If encoding cannot be detected or file is not text.
    """
    raw = path.read_bytes()

    # Try preferred encodings first (fast and accurate)
    for enc in PREFERRED_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback: auto-detect
    result = from_bytes(raw)
    best = result.best()
    if best is None or best.coherence < 0.5:
        raise EncodingDetectionError(str(path))
    return str(best), best.encoding


def atomic_write(path: Path, content: str, encoding: str) -> None:
    """Atomically write to file (using temp file + os.replace).

    Atomic write prevents file corruption if interrupted during write.
    Uses unique temp file names to avoid collisions during concurrent writes.

    Args:
        path: Target file path.
        content: Content to write.
        encoding: Encoding.

    Raises:
        OSError: Raised when write fails.
    """
    # Use uuid to generate unique temp file name, avoiding concurrent write collisions
    unique_suffix = f".{uuid.uuid4().hex[:8]}.tmp"
    temp_path = path.with_suffix(path.suffix + unique_suffix)
    try:
        temp_path.write_text(content, encoding=encoding)
        # os.replace is atomic on POSIX systems
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        raise
