import logging
import os
from collections import Counter
from pathlib import Path

from charset_normalizer import from_bytes

from ..config.fs_policy import ENCODING_DETECTION_IGNORED_DIRS

logger = logging.getLogger(__name__)

TEXT_FILE_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".java",
        ".kt",
        ".kts",
        ".c",
        ".cpp",
        ".cc",
        ".cxx",
        ".h",
        ".hpp",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".cs",
        ".swift",
        ".scala",
        ".lua",
        ".sh",
        ".bash",
        ".zsh",
        ".sql",
        ".html",
        ".htm",
        ".xml",
        ".xhtml",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
        ".txt",
        ".rst",
    }
)

UTF8_COMPATIBLE = frozenset({"utf-8", "ascii", "us-ascii"})


def detect_project_encoding(
    base_dir: Path,
    sample_limit: int = 30,
) -> str | None:
    """Detect the dominant non-UTF-8 encoding in a project."""
    encoding_counts: Counter[str] = Counter()
    files_sampled = 0

    for dirpath, dirnames, filenames in os.walk(base_dir, topdown=True):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and d not in ENCODING_DETECTION_IGNORED_DIRS
        )

        for fname in filenames:
            if files_sampled >= sample_limit:
                break

            ext = os.path.splitext(fname)[1].lower()
            if ext not in TEXT_FILE_EXTENSIONS:
                continue

            file_path = Path(dirpath, fname)
            if file_path.is_symlink() or not file_path.is_file():
                continue

            try:
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

        if files_sampled >= sample_limit:
            break

    if not encoding_counts:
        logger.debug("No files sampled for encoding detection")
        return None

    logger.debug(
        "Encoding detection sampled %d files: %s",
        files_sampled,
        dict(encoding_counts.most_common(5)),
    )

    for enc, count in encoding_counts.most_common():
        if enc not in UTF8_COMPATIBLE:
            ratio = count / files_sampled
            if ratio >= 0.3:
                logger.debug(
                    "Detected project encoding: %s (%.1f%% of sampled files)",
                    enc,
                    ratio * 100,
                )
                return enc

    logger.debug("Project appears to use UTF-8 (no dominant regional encoding)")
    return None
