"""Cloud sync logic for uploading local codebase to Relace Repos."""

import logging
import os
import subprocess  # nosec B404 - used safely with hardcoded commands only
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ...clients.repo import RelaceRepoClient
from ...config import REPO_SYNC_MAX_FILES

logger = logging.getLogger(__name__)

# File extensions to include (common source code)
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".clj",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".rst",
    ".txt",
    ".sql",
    ".graphql",
    ".proto",
    ".cmake",
}

# Special filenames without extensions to include
SPECIAL_FILENAMES = {
    "dockerfile",
    "makefile",
    "cmakelists.txt",
    "gemfile",
    "rakefile",
    "justfile",
    "taskfile",
    "vagrantfile",
    "procfile",
}

# Directories to always exclude
EXCLUDED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".npm",
    ".yarn",
    "venv",
    ".venv",
    "env",
    ".env",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "target",
    "out",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
}

# Maximum file size to upload (1MB)
MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024

# Maximum concurrent uploads
MAX_UPLOAD_WORKERS = 8


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
        # Filter out excluded directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

        for filename in filenames:
            # Skip hidden files
            if filename.startswith("."):
                continue

            file_path = Path(root) / filename
            rel_path = file_path.relative_to(base_path)

            # Check extension or special filename
            ext = file_path.suffix.lower()
            if ext not in CODE_EXTENSIONS and filename.lower() not in SPECIAL_FILENAMES:
                continue

            # Check file size
            try:
                if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            files.append(str(rel_path))

    return files


def _read_file_content(base_dir: str, rel_path: str) -> bytes | None:
    """Read file content as bytes.

    Returns:
        File content, or None if read fails.
    """
    try:
        file_path = Path(base_dir) / rel_path
        if not file_path.is_file():
            return None
        if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
            return None
        return file_path.read_bytes()
    except OSError as exc:
        logger.debug("Failed to read %s: %s", rel_path, exc)
        return None


def cloud_sync_logic(
    client: RelaceRepoClient,
    base_dir: str,
) -> dict[str, Any]:
    """Synchronize local codebase to Relace Cloud.

    Args:
        client: RelaceRepoClient instance.
        base_dir: Base directory to sync.

    Returns:
        Dict containing:
        - repo_id: Repository ID
        - files_uploaded: Number of files uploaded
        - files_skipped: Number of files skipped
        - errors: List of error messages
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Starting cloud sync from %s", trace_id, base_dir)

    errors: list[str] = []
    files_uploaded = 0
    files_skipped = 0

    try:
        # Ensure repo exists
        repo_name = client.get_repo_name_from_base_dir()
        repo_id = client.ensure_repo(repo_name, trace_id=trace_id)
        logger.info("[%s] Using repo '%s' (id=%s)", trace_id, repo_name, repo_id)

        # Get file list (prefer git, fallback to directory scan)
        files = _get_git_tracked_files(base_dir)
        if files is None:
            logger.info("[%s] Git not available, using directory scan", trace_id)
            files = _scan_directory(base_dir)
        else:
            # Filter git files by extension or special filename
            files = [
                f
                for f in files
                if Path(f).suffix.lower() in CODE_EXTENSIONS
                or Path(f).name.lower() in SPECIAL_FILENAMES
            ]

        logger.info("[%s] Found %d files to sync", trace_id, len(files))

        # Limit file count
        if len(files) > REPO_SYNC_MAX_FILES:
            logger.warning(
                "[%s] File count %d exceeds limit %d, truncating",
                trace_id,
                len(files),
                REPO_SYNC_MAX_FILES,
            )
            files = files[:REPO_SYNC_MAX_FILES]

        # Upload files in parallel
        def upload_file(rel_path: str) -> tuple[str, bool, str]:
            """Upload single file, return (path, success, error)."""
            content = _read_file_content(base_dir, rel_path)
            if content is None:
                return (rel_path, False, "Failed to read file")
            try:
                client.upload_file(repo_id, rel_path, content, trace_id=trace_id)
                return (rel_path, True, "")
            except Exception as exc:
                return (rel_path, False, str(exc))

        with ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS) as executor:
            futures = {executor.submit(upload_file, f): f for f in files}

            for future in as_completed(futures):
                rel_path, success, error = future.result()
                if success:
                    files_uploaded += 1
                else:
                    files_skipped += 1
                    if error:
                        errors.append(f"{rel_path}: {error}")

        logger.info(
            "[%s] Cloud sync completed: %d uploaded, %d skipped",
            trace_id,
            files_uploaded,
            files_skipped,
        )

        return {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "files_uploaded": files_uploaded,
            "files_skipped": files_skipped,
            "errors": errors[:10] if errors else [],  # Limit error list
            "total_files": len(files),
        }

    except Exception as exc:
        logger.error("[%s] Cloud sync failed: %s", trace_id, exc)
        return {
            "repo_id": None,
            "files_uploaded": files_uploaded,
            "files_skipped": files_skipped,
            "errors": [str(exc)],
            "error": str(exc),
        }
