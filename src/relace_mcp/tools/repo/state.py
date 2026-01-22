import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_state_dir

from ._git import get_git_remote_origin_url, get_git_root

logger = logging.getLogger(__name__)

# Cross-platform state directory for sync state files
# - Linux: ~/.local/state/relace/sync
# - macOS: ~/Library/Application Support/relace/sync
# - Windows: %LOCALAPPDATA%\relace\sync
_STATE_DIR = Path(user_state_dir("relace", appauthor=False)) / "sync"
_FINGERPRINT_LEN = 12


def _sanitize_repo_name(repo_name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in repo_name)


def get_repo_identity(base_dir: str) -> tuple[str, str, str]:
    """Derive stable identifiers for mapping local projects to cloud/state.

    Returns:
        Tuple of (local_repo_name, cloud_repo_name, project_fingerprint).

    Note:
        - Uses git top-level directory when available.
        - Uses a short SHA-256 fingerprint of (remote.origin.url OR repo_root path).
    """
    repo_root = get_git_root(base_dir)
    local_repo_name = repo_root.name

    origin_url = get_git_remote_origin_url(repo_root)
    identity_source = origin_url or str(repo_root)
    fingerprint = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:_FINGERPRINT_LEN]
    cloud_repo_name = f"{local_repo_name}__{fingerprint}" if local_repo_name else ""
    return local_repo_name, cloud_repo_name, fingerprint


def get_repo_root(base_dir: str) -> str:
    return str(get_git_root(base_dir))


@dataclass
class SyncState:
    """Represents the sync state for a repository."""

    repo_id: str
    repo_head: str
    last_sync: str
    repo_name: str = ""  # Original repo name (for collision detection)
    cloud_repo_name: str = ""  # Cloud repo name used for this project
    project_fingerprint: str = ""  # Fingerprint used for state isolation
    git_branch: str = ""  # Git branch name at sync time (e.g., "main", "HEAD" for detached)
    git_head_sha: str = ""  # Git HEAD commit SHA at sync time
    files: dict[str, str] = field(default_factory=dict)
    skipped_files: set[str] = field(default_factory=set)  # Paths of binary/oversize files
    files_found: int = 0  # Count before applying REPO_SYNC_MAX_FILES limit
    files_selected: int = 0  # Count after applying limit
    file_limit: int = 0  # REPO_SYNC_MAX_FILES used during last sync
    files_truncated: int = 0  # files_found - files_selected when truncated

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "repo_id": self.repo_id,
            "repo_head": self.repo_head,
            "last_sync": self.last_sync,
            "repo_name": self.repo_name,
            "cloud_repo_name": self.cloud_repo_name,
            "project_fingerprint": self.project_fingerprint,
            "git_branch": self.git_branch,
            "git_head_sha": self.git_head_sha,
            "files": self.files,
            "skipped_files": list(self.skipped_files),
            "files_found": self.files_found,
            "files_selected": self.files_selected,
            "file_limit": self.file_limit,
            "files_truncated": self.files_truncated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncState":
        """Create SyncState from dictionary.

        Backward compatible: old state files without newer fields will load with
        empty strings (no crash).
        """
        return cls(
            repo_id=data.get("repo_id", ""),
            repo_head=data.get("repo_head", ""),
            last_sync=data.get("last_sync", ""),
            repo_name=data.get("repo_name", ""),
            cloud_repo_name=data.get("cloud_repo_name", ""),
            project_fingerprint=data.get("project_fingerprint", ""),
            git_branch=data.get("git_branch", ""),
            git_head_sha=data.get("git_head_sha", ""),
            files=data.get("files", {}),
            skipped_files=set(data.get("skipped_files", [])),
            files_found=data.get("files_found", 0),
            files_selected=data.get("files_selected", 0),
            file_limit=data.get("file_limit", 0),
            files_truncated=data.get("files_truncated", 0),
        )


def _get_state_path(repo_name: str, fingerprint: str) -> Path:
    """Get the path to the sync state file for a repository."""
    # Sanitize repo name for filesystem
    safe_name = _sanitize_repo_name(repo_name)
    safe_fp = "".join(c for c in fingerprint.lower() if c.isalnum())
    return _STATE_DIR / f"{safe_name}__{safe_fp}.json"


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


def load_sync_state(base_dir: str) -> SyncState | None:
    """Load sync state from XDG state directory.

    Args:
        base_dir: Base directory of the repository.

    Returns:
        SyncState if found and valid; None otherwise.
    """
    repo_name, cloud_repo_name, fingerprint = get_repo_identity(base_dir)
    if not repo_name:
        logger.debug("No sync state: invalid repo name for base_dir")
        return None

    state_path = _get_state_path(repo_name, fingerprint)

    if not state_path.exists():
        logger.debug("No sync state found for '%s'", repo_name)
        return None

    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        state = SyncState.from_dict(data)

        if state.repo_name and state.repo_name != repo_name:
            logger.warning(
                "Sync state collision: requested '%s' but file contains '%s'. Treating as not found.",
                repo_name,
                state.repo_name,
            )
            return None
        if state.project_fingerprint and state.project_fingerprint != fingerprint:
            logger.warning(
                "Sync state collision: requested fingerprint '%s' but file contains '%s'. Treating as not found.",
                fingerprint,
                state.project_fingerprint,
            )
            return None
        if state.cloud_repo_name and state.cloud_repo_name != cloud_repo_name:
            logger.warning(
                "Sync state mismatch: expected cloud_repo_name '%s' but found '%s'. Treating as not found.",
                cloud_repo_name,
                state.cloud_repo_name,
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


def save_sync_state(base_dir: str, state: SyncState) -> bool:
    """Save sync state to XDG state directory.

    Args:
        base_dir: Base directory of the repository.
        state: SyncState to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    repo_name, cloud_repo_name, fingerprint = get_repo_identity(base_dir)
    if not repo_name:
        logger.error("Failed to save sync state: invalid repo name for base_dir=%s", base_dir)
        return False

    state_path = _get_state_path(repo_name, fingerprint)

    try:
        # Ensure directory exists
        state_path.parent.mkdir(parents=True, exist_ok=True)

        state.repo_name = repo_name
        state.cloud_repo_name = cloud_repo_name
        state.project_fingerprint = fingerprint

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


def clear_sync_state(base_dir: str) -> bool:
    """Remove sync state file for a repository.

    Args:
        base_dir: Base directory of the repository.

    Returns:
        True if removed or didn't exist, False on error.
    """
    repo_name, _cloud_repo_name, fingerprint = get_repo_identity(base_dir)
    if not repo_name:
        logger.error("Failed to clear sync state: invalid repo name for base_dir=%s", base_dir)
        return False

    state_path = _get_state_path(repo_name, fingerprint)
    try:
        state_path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        logger.error("Failed to clear sync state for '%s': %s", repo_name, exc)
        return False
