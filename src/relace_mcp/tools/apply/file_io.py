import logging
import os
import uuid
from pathlib import Path

from charset_normalizer import from_bytes

from .exceptions import EncodingDetectionError

logger = logging.getLogger(__name__)

# Module-level state for project encoding (set by server at startup)
_project_encoding: str | None = None

# Encodings that are effectively UTF-8 for our purposes
_UTF8_COMPATIBLE = frozenset({"utf-8", "utf-8-sig", "ascii", "us-ascii"})


def set_project_encoding(encoding: str | None) -> None:
    """Set the project-level default encoding.

    Called by server during initialization after encoding detection.

    Args:
        encoding: The detected or configured project encoding (e.g., "gbk").
    """
    global _project_encoding
    _project_encoding = encoding.lower() if encoding else None
    if _project_encoding:
        logger.info("Project encoding set to: %s", _project_encoding)


def get_project_encoding() -> str | None:
    """Get the current project-level encoding."""
    return _project_encoding


def _looks_like_binary(data: bytes, sample_size: int = 8192) -> bool:
    """Check if data looks like binary (non-text) content.

    Uses null byte detection and high ratio of non-printable characters.

    Args:
        data: Raw bytes to check.
        sample_size: Number of bytes to sample.

    Returns:
        True if data appears to be binary.
    """
    if not data:
        return False

    sample = data[:sample_size]

    # Null bytes are a strong indicator of binary
    if b"\x00" in sample:
        return True

    # Check ratio of non-text bytes (excluding common control chars)
    # Allow: tab (0x09), newline (0x0a), carriage return (0x0d), and printable ASCII
    non_text_count = 0
    for byte in sample:
        if byte < 0x09 or (0x0E <= byte < 0x20 and byte != 0x1B):  # Allow ESC for ANSI
            non_text_count += 1

    # If more than 30% non-text bytes, likely binary
    if len(sample) > 0 and non_text_count / len(sample) > 0.30:
        return True

    return False


def _detect_declared_encoding(path: Path, raw: bytes) -> str | None:
    """Detect a file-declared encoding (when available).

    For Python files, prefer the PEP 263 coding cookie / BOM via tokenize.detect_encoding.
    Returns None when no declaration is found or detection fails.
    """
    if path.suffix.lower() not in {".py", ".pyi"}:
        return None

    # tokenize.detect_encoding is the canonical implementation for Python source encoding.
    # It handles UTF-8 BOM and coding cookies on the first two lines.
    try:
        import io
        import tokenize

        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        return encoding.lower() if encoding else None
    except Exception:
        return None


def decode_text_with_fallback(
    raw: bytes,
    *,
    path: Path | None = None,
    preferred_encoding: str | None = None,
    min_coherence: float = 0.5,
) -> tuple[str, str]:
    """Decode bytes into text with best-effort encoding detection.

    Strategy (ordered):
    1) Reject likely-binary files
    2) Honor declared encoding for Python source (PEP 263)
    3) UTF-8 (common default)
    4) charset_normalizer detection (handles GBK/Big5/etc reliably vs naive fallbacks)
    5) Preferred encoding as last resort (if set)

    Returns:
        (decoded_text, encoding_name_lowercase)

    Raises:
        EncodingDetectionError: When decoding cannot be performed confidently.
    """
    if _looks_like_binary(raw):
        raise EncodingDetectionError(str(path) if path else "<bytes>")

    preferred = preferred_encoding.lower() if preferred_encoding else None

    declared = _detect_declared_encoding(path, raw) if path else None
    if declared and declared not in _UTF8_COMPATIBLE:
        try:
            return raw.decode(declared), declared
        except (UnicodeDecodeError, LookupError):
            # Fall through to other strategies
            pass

    # Fast path: UTF-8
    try:
        text = raw.decode("utf-8")
        # If the project encoding is configured and the file is ASCII-only, preserve
        # the project encoding to keep newly written non-ASCII content consistent.
        if preferred and preferred not in _UTF8_COMPATIBLE and text.isascii():
            return text, preferred
        return text, "utf-8"
    except UnicodeDecodeError:
        pass

    def encoding_family(enc: str) -> str:
        e = enc.lower()
        if e.startswith("gb") or e in {"hz-gb-2312", "hz"}:
            return "gb"
        if "big5" in e or e in {"cp950"}:
            return "big5"
        return "other"

    preferred_text: str | None = None
    if preferred and preferred not in _UTF8_COMPATIBLE:
        try:
            preferred_text = raw.decode(preferred)
        except (UnicodeDecodeError, LookupError):
            preferred_text = None

    # Robust path: charset_normalizer (helps distinguish GBK vs Big5 without naive fallbacks)
    result = from_bytes(raw)
    best = result.best()
    if best is not None and best.encoding:
        best_enc = best.encoding.lower()
        best_ok = best.coherence >= min_coherence

        if preferred_text is not None:
            # Type narrowing: preferred_text is not None implies preferred is not None
            # (due to the check at line 149: `if preferred and preferred not in _UTF8_COMPATIBLE`)
            assert preferred is not None  # nosec B101 - type narrowing only
            # When a project encoding is explicitly configured/detected, prefer it unless
            # charset_normalizer is strongly confident it's a different encoding family.
            if encoding_family(preferred) == encoding_family(best_enc):
                return preferred_text, preferred

            override_ok = best.coherence >= max(min_coherence, 0.5)
            if best_ok and override_ok:
                return str(best), best_enc
            return preferred_text, preferred

        if best_ok:
            return str(best), best_enc

    # Last resort: preferred encoding (if configured/detected)
    if preferred_text is not None:
        assert preferred is not None  # nosec B101 - type narrowing only
        return preferred_text, preferred

    raise EncodingDetectionError(str(path) if path else "<bytes>")


def decode_text_best_effort(
    raw: bytes,
    *,
    path: Path | None = None,
    preferred_encoding: str | None = None,
    errors: str = "replace",
) -> str | None:
    """Decode bytes into text for display/search/sync.

    Returns None for likely-binary content. Never raises due to decoding.
    """
    if _looks_like_binary(raw):
        return None

    try:
        text, _ = decode_text_with_fallback(
            raw,
            path=path,
            preferred_encoding=preferred_encoding,
            min_coherence=0.2,
        )
        return text
    except EncodingDetectionError:
        # As a last resort, return a lossy UTF-8 decode for robustness.
        return raw.decode("utf-8", errors=errors)


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    """Read text file with automatic encoding detection.

    Strategy:
    1) Reject likely-binary files (fast heuristic)
    2) Honor Python source declarations (PEP 263)
    3) Try UTF-8
    4) Use charset_normalizer detection for legacy encodings (GBK/Big5/etc)
    5) Prefer configured project encoding when appropriate

    Args:
        path: File path.

    Returns:
        (content, encoding) tuple.

    Raises:
        EncodingDetectionError: If encoding cannot be detected or file is not text.
    """
    raw = path.read_bytes()
    return decode_text_with_fallback(
        raw,
        path=path,
        preferred_encoding=_project_encoding,
        # Be tolerant here: binary files are filtered earlier, and short source files
        # can yield very low coherence scores even when the encoding is correct.
        min_coherence=0.0,
    )


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
        # Use open with newline='' to preserve original line endings on all platforms.
        # Without this, Windows would convert \n to \r\n in text mode.
        with temp_path.open("w", encoding=encoding, newline="") as f:
            f.write(content)
        # os.replace is atomic on POSIX systems
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        raise
