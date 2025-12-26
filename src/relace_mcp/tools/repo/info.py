import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from .state import get_current_git_info, load_sync_state

logger = logging.getLogger(__name__)


def cloud_info_logic(
    client: RelaceRepoClient,
    base_dir: str,
) -> dict[str, Any]:
    """Get current repository sync status and cloud info.

    Integrates: local sync state + current git ref + list summary (if cloud repo exists)

    Args:
        client: RelaceRepoClient instance.
        base_dir: Base directory of the repository.

    Returns:
        Dict containing:
        - repo_name: Repository name (derived from base_dir)
        - local: Current local git state
        - synced: Last synced state (from local cache)
        - cloud: Cloud repo info (if found in list)
        - status: Sync status and recommended action
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    repo_name = client.get_repo_name_from_base_dir(base_dir)
    logger.info("[%s] Getting cloud info for '%s'", trace_id, repo_name)

    try:
        # Get current git info
        current_branch, current_head = get_current_git_info(base_dir)

        # Load local sync state
        sync_state = load_sync_state(repo_name)

        # Build local info
        local_info = {
            "git_branch": current_branch,
            "git_head": current_head[:8] if current_head else "",
        }

        # Build synced info from local state
        synced_info = None
        if sync_state:
            synced_info = {
                "repo_id": sync_state.repo_id,
                "repo_head": sync_state.repo_head[:8] if sync_state.repo_head else "",
                "git_branch": sync_state.git_branch,
                "git_head": sync_state.git_head_sha[:8] if sync_state.git_head_sha else "",
                "last_sync": sync_state.last_sync,
                "tracked_files": len(sync_state.files),
                "skipped_files": len(sync_state.skipped_files),
            }

        # Try to find cloud repo in list
        cloud_info = None
        try:
            repos = client.list_repos(trace_id=trace_id)
            for repo in repos:
                metadata = repo.get("metadata") or {}
                name = metadata.get("name") or repo.get("name")
                if name == repo_name:
                    cloud_info = {
                        "repo_id": repo.get("repo_id") or repo.get("id"),
                        "auto_index": repo.get("auto_index"),
                        "created_at": repo.get("created_at"),
                        "updated_at": repo.get("updated_at"),
                    }
                    break
        except Exception as exc:
            logger.warning("[%s] Failed to fetch cloud repos: %s", trace_id, exc)

        # Determine status
        ref_changed = False
        needs_sync = False
        recommended_action = None

        if sync_state and current_head:
            old_head = sync_state.git_head_sha
            if old_head and old_head != current_head:
                ref_changed = True
                needs_sync = True
                recommended_action = (
                    "Git HEAD changed since last sync. "
                    "Run cloud_sync() for safe sync, or "
                    "cloud_sync(force=True, mirror=True) to fully align with current branch."
                )
        elif not sync_state:
            needs_sync = True
            recommended_action = "No sync state found. Run cloud_sync() to upload codebase."

        status_info = {
            "ref_changed": ref_changed,
            "needs_sync": needs_sync,
            "recommended_action": recommended_action,
        }

        logger.info(
            "[%s] Info retrieved: synced=%s, cloud=%s, ref_changed=%s",
            trace_id,
            synced_info is not None,
            cloud_info is not None,
            ref_changed,
        )

        return {
            "repo_name": repo_name,
            "local": local_info,
            "synced": synced_info,
            "cloud": cloud_info,
            "status": status_info,
        }

    except Exception as exc:
        logger.error("[%s] Cloud info failed: %s", trace_id, exc)
        return {
            "repo_name": repo_name,
            "local": None,
            "synced": None,
            "cloud": None,
            "status": None,
            "error": str(exc),
        }
