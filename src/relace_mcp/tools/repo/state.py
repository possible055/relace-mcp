import hashlib
import json
import logging
import subprocess  # nosec B404 - used safely with hardcoded commands only
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_state_dir

logger = logging.getLogger(__name__)

# Cross-platform state directory for sync state files
# - Linux: ~/.local/state/relace/sync
# - macOS: ~/Library/Application Support/relace/sync
# - Windows: %LOCALAPPDATA%\relace\sync
_STATE_DIR = Path(user_state_dir("relace", appauthor=False)) / "sync"


@dataclass
class SyncState:
    """Represents the sync state for a repository."""

    repo_id: str
    repo_head: str
    last_sync: str
    repo_name: str = ""  # Original repo name (for collision detection)
    git_branch: str = ""  # Git branch name at sync time (e.g., "main", "HEAD" for detached)
    git_head_sha: str = ""  # Git HEAD commit SHA at sync time
    files: dict[str, str] = field(default_factory=dict)
    skipped_files: set[str] = field(default_factory=set)  # Paths of binary/oversize files

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "repo_id": self.repo_id,
            "repo_head": self.repo_head,
            "last_sync": self.last_sync,
            "repo_name": self.repo_name,
            "git_branch": self.git_branch,
            "git_head_sha": self.git_head_sha,
            "files": self.files,
            "skipped_files": list(self.skipped_files),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncState":
        """Create SyncState from dictionary.

        Backward compatible: old state files without repo_name/git_branch/git_head_sha
        will load with empty strings (no crash).
        """
        return cls(
            repo_id=data.get("repo_id", ""),
            repo_head=data.get("repo_head", ""),
            last_sync=data.get("last_sync", ""),
            repo_name=data.get("repo_name", ""),
            git_branch=data.get("git_branch", ""),
            git_head_sha=data.get("git_head_sha", ""),
            files=data.get("files", {}),
            skipped_files=set(data.get("skipped_files", [])),
        )


def _get_state_path(repo_name: str) -> Path:
    """Get the path to the sync state file for a repository."""
    # Sanitize repo name for filesystem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in repo_name)
    return _STATE_DIR / f"{safe_name}.json"


def compute_file_hash(file_path: Path) -> str | None:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hash string prefixed with "sha256:", or None if file cannot be read.
    """
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"
    except OSError as exc:
        logger.debug("Failed to hash %s: %s", file_path, exc)
        return None


def load_sync_state(repo_name: str) -> SyncState | None:
    """Load sync state from XDG state directory.

    Args:
        repo_name: Repository name.

    Returns:
        SyncState if found, valid, and repo_name matches; None otherwise.

    Note:
        Returns None if the stored repo_name doesn't match the requested one.
        This prevents collisions where sanitized filenames overlap
        (e.g., 'my.project' and 'my_project' both map to 'my_project.json').
    """
    state_path = _get_state_path(repo_name)

    if not state_path.exists():
        logger.debug("No sync state found for '%s'", repo_name)
        return None

    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        state = SyncState.from_dict(data)

        # Validate repo_name matches to prevent collision attacks.
        # Old state files without repo_name are accepted for backward compat.
        if state.repo_name and state.repo_name != repo_name:
            logger.warning(
                "Sync state collision: requested '%s' but file contains '%s'. "
                "Treating as not found to prevent cross-repo operations.",
                repo_name,
                state.repo_name,
            )
            return None

        logger.debug(
            "Loaded sync state for '%s': %d files, head=%s",
            repo_name,
            len(state.files),
            state.repo_head[:8] if state.repo_head else "none",
        )
        return state
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to load sync state for '%s': %s", repo_name, exc)
        return None


def save_sync_state(repo_name: str, state: SyncState) -> bool:
    """Save sync state to XDG state directory.

    Args:
        repo_name: Repository name.
        state: SyncState to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    state_path = _get_state_path(repo_name)

    try:
        # Ensure directory exists
        state_path.parent.mkdir(parents=True, exist_ok=True)

        # Set repo_name for collision detection on load
        state.repo_name = repo_name

        # Update last_sync timestamp
        state.last_sync = datetime.now(UTC).isoformat()

        # Write atomically using temp file
        temp_path = state_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)
        temp_path.replace(state_path)

        logger.debug(
            "Saved sync state for '%s': %d files, head=%s",
            repo_name,
            len(state.files),
            state.repo_head[:8] if state.repo_head else "none",
        )
        return True
    except OSError as exc:
        logger.error("Failed to save sync state for '%s': %s", repo_name, exc)
        return False


def clear_sync_state(repo_name: str) -> bool:
    """Remove sync state file for a repository.

    Args:
        repo_name: Repository name.

    Returns:
        True if removed or didn't exist, False on error.
    """
    state_path = _get_state_path(repo_name)
    try:
        state_path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        logger.error("Failed to clear sync state for '%s': %s", repo_name, exc)
        return False


def get_current_git_info(base_dir: str) -> tuple[str, str]:
    """Get current Git branch name and HEAD commit SHA.

    Handles:
    - Normal branch: returns ("main", "abc123...")
    - Detached HEAD: returns ("HEAD", "abc123...")
    - Non-git project or git unavailable: returns ("", "")

    Args:
        base_dir: Base directory of the repository.

    Returns:
        Tuple of (branch_name, head_sha). Either or both may be empty strings.
    """
    branch = ""
    head_sha = ""

    try:
        # Get branch name (symbolic ref)
        # --abbrev-ref HEAD returns branch name, or "HEAD" if detached
        result = subprocess.run(  # nosec B603 B607 - hardcoded command
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()

        # Get HEAD commit SHA
        result = subprocess.run(  # nosec B603 B607 - hardcoded command
            ["git", "rev-parse", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            head_sha = result.stdout.strip()

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("Failed to get git info from %s: %s", base_dir, exc)

    return branch, head_sha
