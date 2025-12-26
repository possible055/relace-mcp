import logging
from collections import Counter
from pathlib import Path

from charset_normalizer import from_bytes

logger = logging.getLogger(__name__)

# File extensions to sample for encoding detection
TEXT_FILE_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",  # Python
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",  # JavaScript/TypeScript
        ".java",
        ".kt",
        ".kts",  # JVM
        ".c",
        ".cpp",
        ".cc",
        ".cxx",
        ".h",
        ".hpp",  # C/C++
        ".go",  # Go
        ".rs",  # Rust
        ".rb",  # Ruby
        ".php",  # PHP
        ".cs",  # C#
        ".swift",  # Swift
        ".scala",  # Scala
        ".lua",  # Lua
        ".sh",
        ".bash",
        ".zsh",  # Shell
        ".sql",  # SQL
        ".html",
        ".htm",
        ".xml",
        ".xhtml",  # Markup
        ".css",
        ".scss",
        ".sass",
        ".less",  # Styles
        ".json",
        ".yaml",
        ".yml",
        ".toml",  # Config
        ".md",
        ".txt",
        ".rst",  # Text
    }
)

# Encodings that are essentially compatible with UTF-8 (ASCII subset)
UTF8_COMPATIBLE = frozenset({"utf-8", "ascii", "us-ascii"})


def detect_project_encoding(
    base_dir: Path,
    sample_limit: int = 30,
) -> str | None:
    """Detect the dominant non-UTF-8 encoding in a project.

    Scans a sample of text files in the project directory to determine
    if a regional encoding (e.g., GBK, Big5, Shift_JIS) is predominantly used.

    Args:
        base_dir: Project root directory to scan.
        sample_limit: Maximum number of files to sample.

    Returns:
        The detected encoding name (lowercase) if a non-UTF-8 encoding
        is dominant, or None if the project appears to use UTF-8.
    """
    encoding_counts: Counter[str] = Counter()
    files_sampled = 0

    # Walk through files, prioritizing source code
    for file_path in base_dir.rglob("*"):
        if files_sampled >= sample_limit:
            break

        # Skip non-files, hidden files, and common non-source directories
        # Skip symlinks to prevent path traversal attacks and infinite loops
        if file_path.is_symlink():
            continue
        if not file_path.is_file():
            continue
        if any(part.startswith(".") for part in file_path.parts):
            continue
        if any(
            part in {"node_modules", "__pycache__", "venv", ".venv", "dist", "build"}
            for part in file_path.parts
        ):
            continue

        # Only sample known text file extensions
        if file_path.suffix.lower() not in TEXT_FILE_EXTENSIONS:
            continue

        try:
            # Read first 8KB for detection (enough for charset detection)
            raw = file_path.read_bytes()[:8192]
            if not raw:
                continue

            result = from_bytes(raw).best()
            if result and result.encoding:
                enc = result.encoding.lower()
                encoding_counts[enc] += 1
                files_sampled += 1
                logger.debug("Detected encoding %s for %s", enc, file_path)
        except (OSError, PermissionError) as exc:
            logger.debug("Skipping %s: %s", file_path, exc)
            continue

    if not encoding_counts:
        logger.info("No files sampled for encoding detection")
        return None

    logger.info(
        "Encoding detection sampled %d files: %s",
        files_sampled,
        dict(encoding_counts.most_common(5)),
    )

    # Find the most common non-UTF-8 encoding
    for enc, count in encoding_counts.most_common():
        if enc not in UTF8_COMPATIBLE:
            # If non-UTF-8 encoding appears in at least 30% of sampled files
            ratio = count / files_sampled
            if ratio >= 0.3:
                logger.info(
                    "Detected project encoding: %s (%.1f%% of sampled files)",
                    enc,
                    ratio * 100,
                )
                return enc

    logger.info("Project appears to use UTF-8 (no dominant regional encoding)")
    return None
