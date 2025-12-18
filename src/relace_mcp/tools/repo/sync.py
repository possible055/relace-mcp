import logging
import os
import subprocess  # nosec B404 - used safely with hardcoded commands only
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ...clients.repo import RelaceRepoClient
from ...config import REPO_SYNC_MAX_FILES
from .state import SyncState, compute_file_hash, load_sync_state, save_sync_state

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


def _compute_file_hashes(
    base_dir: str,
    files: list[str],
) -> dict[str, str]:
    """Compute SHA-256 hashes for files in parallel.

    Args:
        base_dir: Base directory path.
        files: List of relative file paths.

    Returns:
        Dict mapping relative path to "sha256:..." hash.
    """
    hashes: dict[str, str] = {}

    def hash_file(rel_path: str) -> tuple[str, str | None]:
        file_path = Path(base_dir) / rel_path
        file_hash = compute_file_hash(file_path)
        return (rel_path, file_hash)

    with ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS) as executor:
        futures = [executor.submit(hash_file, f) for f in files]
        for future in as_completed(futures):
            rel_path, file_hash = future.result()
            if file_hash:
                hashes[rel_path] = file_hash

    return hashes


def _compute_diff_operations(
    base_dir: str,
    current_files: dict[str, str],
    cached_state: SyncState | None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Compute diff operations between current files and cached state.

    Args:
        base_dir: Base directory path.
        current_files: Dict mapping relative path to hash.
        cached_state: Previous sync state, or None for full sync.

    Returns:
        Tuple of (operations list, new file hashes for all files).
    """
    operations: list[dict[str, Any]] = []
    new_hashes: dict[str, str] = {}

    # Get cached file hashes
    cached_files = cached_state.files if cached_state else {}

    # Find files to write (new or modified)
    for rel_path, current_hash in current_files.items():
        cached_hash = cached_files.get(rel_path)
        if cached_hash != current_hash:
            # File is new or modified, read content
            content = _read_file_content(base_dir, rel_path)
            if content is not None:
                # Decode to string for API (assuming UTF-8)
                try:
                    content_str = content.decode("utf-8")
                except UnicodeDecodeError:
                    # Skip binary files that can't be decoded
                    logger.debug("Skipping binary file: %s", rel_path)
                    continue
                operations.append(
                    {
                        "type": "write",
                        "filename": rel_path,
                        "content": content_str,
                    }
                )
                new_hashes[rel_path] = current_hash
        else:
            # File unchanged
            new_hashes[rel_path] = current_hash

    # Find files to delete (in cache but not in current)
    for rel_path in cached_files:
        if rel_path not in current_files:
            file_path = Path(base_dir) / rel_path
            if file_path.exists():
                # File exists but hash failed (permission issue, etc.)
                # Skip deletion to avoid data loss
                logger.warning("Skipping delete for %s: file exists but hash failed", rel_path)
                continue
            operations.append(
                {
                    "type": "delete",
                    "filename": rel_path,
                }
            )

    return operations, new_hashes


def cloud_sync_logic(
    client: RelaceRepoClient,
    base_dir: str,
    force: bool = False,
) -> dict[str, Any]:
    """Synchronize local codebase to Relace Cloud with incremental support.

    Args:
        client: RelaceRepoClient instance.
        base_dir: Base directory to sync.
        force: If True, force full sync ignoring cached state.

    Returns:
        Dict containing:
        - repo_id: Repository ID
        - repo_name: Repository name
        - repo_head: New repo head after sync
        - is_incremental: Whether incremental sync was used
        - files_created: Number of new files
        - files_updated: Number of modified files
        - files_deleted: Number of deleted files
        - files_unchanged: Number of unchanged files
        - total_files: Total files in sync
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Starting cloud sync from %s (force=%s)", trace_id, base_dir, force)

    try:
        # Ensure repo exists
        repo_name = client.get_repo_name_from_base_dir()
        repo_id = client.ensure_repo(repo_name, trace_id=trace_id)
        logger.info("[%s] Using repo '%s' (id=%s)", trace_id, repo_name, repo_id)

        # Load cached sync state (unless force)
        cached_state: SyncState | None = None
        if not force:
            cached_state = load_sync_state(repo_name)
            if cached_state and cached_state.repo_id != repo_id:
                # Repo ID mismatch, force full sync
                logger.warning(
                    "[%s] Cached repo_id mismatch, forcing full sync",
                    trace_id,
                )
                cached_state = None

        is_incremental = cached_state is not None

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

        logger.info("[%s] Found %d files to process", trace_id, len(files))

        # Limit file count
        if len(files) > REPO_SYNC_MAX_FILES:
            logger.warning(
                "[%s] File count %d exceeds limit %d, truncating",
                trace_id,
                len(files),
                REPO_SYNC_MAX_FILES,
            )
            files = files[:REPO_SYNC_MAX_FILES]

        # Compute file hashes
        logger.info("[%s] Computing file hashes...", trace_id)
        current_hashes = _compute_file_hashes(base_dir, files)

        # Compute diff operations
        operations, new_hashes = _compute_diff_operations(base_dir, current_hashes, cached_state)

        # Count operation types
        writes = [op for op in operations if op["type"] == "write"]
        deletes = [op for op in operations if op["type"] == "delete"]

        # Determine creates vs updates
        cached_files = cached_state.files if cached_state else {}
        files_created = sum(1 for op in writes if op["filename"] not in cached_files)
        files_updated = sum(1 for op in writes if op["filename"] in cached_files)
        files_deleted = len(deletes)
        files_unchanged = len(new_hashes) - len(writes)

        logger.info(
            "[%s] Diff computed: %d created, %d updated, %d deleted, %d unchanged",
            trace_id,
            files_created,
            files_updated,
            files_deleted,
            files_unchanged,
        )

        # Apply changes
        repo_head = ""
        if operations:
            logger.info("[%s] Applying %d operations via update API...", trace_id, len(operations))
            result = client.update_repo(repo_id, operations, trace_id=trace_id)
            repo_head = result.get("repo_head", "")
            logger.info(
                "[%s] Update completed, new head=%s",
                trace_id,
                repo_head[:8] if repo_head else "none",
            )
        else:
            logger.info("[%s] No changes detected, skipping update", trace_id)
            repo_head = cached_state.repo_head if cached_state else ""

        # Save new sync state
        new_state = SyncState(
            repo_id=repo_id,
            repo_head=repo_head,
            last_sync="",  # Will be set by save_sync_state
            files=new_hashes,
        )
        save_sync_state(repo_name, new_state)

        return {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "repo_head": repo_head,
            "is_incremental": is_incremental,
            "files_created": files_created,
            "files_updated": files_updated,
            "files_deleted": files_deleted,
            "files_unchanged": files_unchanged,
            "total_files": len(new_hashes),
        }

    except Exception as exc:
        logger.error("[%s] Cloud sync failed: %s", trace_id, exc)
        return {
            "repo_id": None,
            "repo_name": client.get_repo_name_from_base_dir(),
            "repo_head": None,
            "is_incremental": False,
            "files_created": 0,
            "files_updated": 0,
            "files_deleted": 0,
            "files_unchanged": 0,
            "total_files": 0,
            "error": str(exc),
        }
