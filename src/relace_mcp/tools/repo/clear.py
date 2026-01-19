import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from .errors import build_cloud_error_details
from .logging import (
    log_cloud_clear_complete,
    log_cloud_clear_error,
    log_cloud_clear_start,
)
from .state import clear_sync_state, get_repo_identity, load_sync_state

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
        result = {
            "trace_id": trace_id,
            "status": "cancelled",
            "message": "Operation cancelled. Access to this tool requires 'confirm=True' to proceed with irreversible deletion.",
            "repo_id": None,
        }
        log_cloud_clear_start(trace_id, None, None, confirm=False)
        log_cloud_clear_complete(trace_id, result)
        return result

    local_repo_name: str | None = None
    cloud_repo_name: str | None = None

    try:
        local_repo_name, cloud_repo_name, _project_fingerprint = get_repo_identity(base_dir)
        if not local_repo_name or not cloud_repo_name:
            result = {
                "trace_id": trace_id,
                "status": "error",
                "message": "Invalid base_dir: cannot derive repository name from root, current directory, or empty path.",
                "repo_id": None,
            }
            log_cloud_clear_start(trace_id, None, None, confirm=True)
            log_cloud_clear_error(trace_id, None, None, result)
            return result

        log_cloud_clear_start(trace_id, local_repo_name, cloud_repo_name, confirm=True)

        # 1. Try to get repo_id from local sync state (safest)
        repo_id = None
        sync_state = load_sync_state(base_dir)
        if sync_state:
            repo_id = sync_state.repo_id
            logger.info("[%s] Found repo_id %s from local sync state", trace_id, repo_id)

        # 2. Fallback: Search by name (riskier, but needed if local state is missing)
        if not repo_id:
            logger.warning(
                "[%s] No local sync state found for '%s', searching API...",
                trace_id,
                local_repo_name,
            )
            repos = client.list_repos(trace_id=trace_id)
            matching_repos = []
            for r in repos:
                # Handle different API response structures if necessary
                metadata = r.get("metadata") or {}
                r_name = metadata.get("name") or r.get("name")
                if r_name == cloud_repo_name:
                    matching_repos.append(r)

            if len(matching_repos) > 1:
                logger.error(
                    "[%s] Multiple repos found with name '%s', aborting unsafe delete",
                    trace_id,
                    cloud_repo_name,
                )
                result = {
                    "trace_id": trace_id,
                    "status": "error",
                    "message": f"Multiple repositories found with name '{cloud_repo_name}'. Cannot safely delete unambiguously.",
                    "repo_name": local_repo_name,
                    "cloud_repo_name": cloud_repo_name,
                }
                log_cloud_clear_complete(trace_id, result)
                return result

            if matching_repos:
                r = matching_repos[0]
                repo_id = r.get("repo_id") or r.get("id")

        if not repo_id:
            logger.info("[%s] No repository found for '%s'", trace_id, cloud_repo_name)
            # Even if repo not found remotely, ensure local state is clean
            clear_sync_state(base_dir)
            result = {
                "trace_id": trace_id,
                "status": "not_found",
                "message": f"Repository '{cloud_repo_name}' not found on cloud.",
                "repo_name": local_repo_name,
                "cloud_repo_name": cloud_repo_name,
            }
            log_cloud_clear_complete(trace_id, result)
            return result

        # 3. specific deletion
        logger.info("[%s] Deleting repo '%s' (%s)...", trace_id, cloud_repo_name, repo_id)
        if client.delete_repo(repo_id, trace_id=trace_id):
            # 4. Clear local state only after successful remote deletion
            clear_sync_state(base_dir)
            result = {
                "trace_id": trace_id,
                "status": "deleted",
                "message": f"Repository '{cloud_repo_name}' ({repo_id}) and local sync state deleted successfully.",
                "repo_name": local_repo_name,
                "cloud_repo_name": cloud_repo_name,
                "repo_id": repo_id,
            }
            log_cloud_clear_complete(trace_id, result)
            return result
        else:
            result = {
                "trace_id": trace_id,
                "status": "error",
                "message": f"Failed to delete repository '{cloud_repo_name}' ({repo_id}).",
                "repo_name": local_repo_name,
                "cloud_repo_name": cloud_repo_name,
                "repo_id": repo_id,
            }
            log_cloud_clear_complete(trace_id, result)
            return result

    except Exception as exc:
        logger.error("[%s] Cloud clear failed: %s", trace_id, exc)
        result = {
            "trace_id": trace_id,
            "status": "error",
            "message": f"Operation failed: {str(exc)}",
            "error": str(exc),
            **build_cloud_error_details(exc),
        }
        log_cloud_clear_error(trace_id, local_repo_name, cloud_repo_name, result)
        return result
