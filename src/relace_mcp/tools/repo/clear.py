import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from .state import clear_sync_state, load_sync_state

logger = logging.getLogger(__name__)


def cloud_clear_logic(
    client: RelaceRepoClient,
    base_dir: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Clear (delete) the cloud repository and local sync state.

    Args:
        client: RelaceRepoClient instance.
        base_dir: Base directory of the repository.
        confirm: Confirmation flag to proceed with deletion.

    Returns:
        Dict containing operation result.
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Starting cloud clear from %s", trace_id, base_dir)

    if not confirm:
        return {
            "status": "cancelled",
            "message": "Operation cancelled. Access to this tool requires 'confirm=True' to proceed with irreversible deletion.",
            "repo_id": None,
        }

    try:
        repo_name = client.get_repo_name_from_base_dir(base_dir)

        # 1. Try to get repo_id from local sync state (safest)
        repo_id = None
        sync_state = load_sync_state(repo_name)
        if sync_state:
            repo_id = sync_state.repo_id
            logger.info("[%s] Found repo_id %s from local sync state", trace_id, repo_id)

        # 2. Fallback: Search by name (riskier, but needed if local state is missing)
        if not repo_id:
            logger.warning(
                "[%s] No local sync state found for '%s', searching API...", trace_id, repo_name
            )
            repos = client.list_repos(trace_id=trace_id)
            matching_repos = []
            for r in repos:
                # Handle different API response structures if necessary
                metadata = r.get("metadata") or {}
                r_name = metadata.get("name") or r.get("name")
                if r_name == repo_name:
                    matching_repos.append(r)

            if len(matching_repos) > 1:
                logger.error(
                    "[%s] Multiple repos found with name '%s', aborting unsafe delete",
                    trace_id,
                    repo_name,
                )
                return {
                    "status": "error",
                    "message": f"Multiple repositories found with name '{repo_name}'. Cannot safely delete unambiguously.",
                    "repo_name": repo_name,
                }

            if matching_repos:
                r = matching_repos[0]
                repo_id = r.get("repo_id") or r.get("id")

        if not repo_id:
            logger.info("[%s] No repository found for '%s'", trace_id, repo_name)
            # Even if repo not found remotely, ensure local state is clean
            clear_sync_state(repo_name)
            return {
                "status": "not_found",
                "message": f"Repository '{repo_name}' not found on cloud.",
                "repo_name": repo_name,
            }

        # 3. specific deletion
        logger.info("[%s] Deleting repo '%s' (%s)...", trace_id, repo_name, repo_id)
        if client.delete_repo(repo_id, trace_id=trace_id):
            # 4. Clear local state only after successful remote deletion
            clear_sync_state(repo_name)
            return {
                "status": "deleted",
                "message": f"Repository '{repo_name}' ({repo_id}) and local sync state deleted successfully.",
                "repo_name": repo_name,
                "repo_id": repo_id,
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to delete repository '{repo_name}' ({repo_id}).",
                "repo_name": repo_name,
                "repo_id": repo_id,
            }

    except Exception as exc:
        logger.error("[%s] Cloud clear failed: %s", trace_id, exc)
        return {
            "status": "error",
            "message": f"Operation failed: {str(exc)}",
            "error": str(exc),
        }
