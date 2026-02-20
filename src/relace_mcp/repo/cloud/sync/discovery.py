import logging
import os
import subprocess  # nosec B404 - used safely with hardcoded commands only
from pathlib import Path

from .constants import (
    CODE_EXTENSIONS,
    EXCLUDED_DIRS,
    SPECIAL_FILENAMES,
    SYNC_MAX_FILE_SIZE_BYTES,
)

logger = logging.getLogger(__name__)


def _get_git_tracked_files(base_dir: str) -> list[str] | None:
    """Get list of git-tracked files using git ls-files.

    Returns:
        List of relative file paths, or None if git command fails.
    """
    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded command, no user input
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            return files
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("git ls-files failed: %s", exc)
    return None


def _scan_directory(base_dir: str) -> list[str]:
    """Fallback directory scanning when git is not available.

    Returns:
        List of relative file paths.
    """
    files: list[str] = []
    base_path = Path(base_dir)

    for root, dirs, filenames in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

        for filename in filenames:
            if filename.startswith("."):
                continue

            file_path = Path(root) / filename
            rel_path = file_path.relative_to(base_path)

            ext = file_path.suffix.lower()
            if ext not in CODE_EXTENSIONS and filename.lower() not in SPECIAL_FILENAMES:
                continue

            try:
                if file_path.stat().st_size > SYNC_MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            files.append(rel_path.as_posix())

    return files
