import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# XDG state directory for sync state files
_XDG_STATE_HOME = Path.home() / ".local" / "state" / "relace" / "sync"


@dataclass
class SyncState:
    """Represents the sync state for a repository."""

    repo_id: str
    repo_head: str
    last_sync: str
    files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "repo_id": self.repo_id,
            "repo_head": self.repo_head,
            "last_sync": self.last_sync,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncState":
        """Create SyncState from dictionary."""
        return cls(
            repo_id=data.get("repo_id", ""),
            repo_head=data.get("repo_head", ""),
            last_sync=data.get("last_sync", ""),
            files=data.get("files", {}),
        )


def _get_state_path(repo_name: str) -> Path:
    """Get the path to the sync state file for a repository."""
    # Sanitize repo name for filesystem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in repo_name)
    return _XDG_STATE_HOME / f"{safe_name}.json"


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
        SyncState if found and valid, None otherwise.
    """
    state_path = _get_state_path(repo_name)

    if not state_path.exists():
        logger.debug("No sync state found for '%s'", repo_name)
        return None

    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        state = SyncState.from_dict(data)
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
