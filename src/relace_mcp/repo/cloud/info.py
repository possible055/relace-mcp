import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from ..core import (
    _extract_error_fields,
    build_cloud_error_details,
    get_current_git_info,
    get_repo_identity,
    is_git_dirty,
    load_sync_state,
    log_cloud_event,
)

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
    local_repo_name, cloud_repo_name, _project_fingerprint = get_repo_identity(base_dir)
    logger.debug("[%s] Getting cloud info for repository", trace_id)

    try:
        if not local_repo_name or not cloud_repo_name:
            result = {
                "trace_id": trace_id,
                "repo_name": local_repo_name or None,
                "cloud_repo_name": None,
                "local": None,
                "synced": None,
                "cloud": None,
                "status": None,
                "error": "Invalid base_dir: cannot derive repository name.",
            }
            log_cloud_event(
                "cloud_info_error",
                trace_id,
                repo_name=local_repo_name or None,
                cloud_repo_name=None,
                **_extract_error_fields(result),
            )
            return result

        log_cloud_event(
            "cloud_info_start",
            trace_id,
            repo_name=local_repo_name,
            cloud_repo_name=cloud_repo_name,
        )

        # Get current git info
        current_branch, current_head = get_current_git_info(base_dir)
        git_dirty = is_git_dirty(base_dir)

        # Load local sync state
        sync_state = load_sync_state(base_dir)

        # Build local info
        local_info = {
            "git_branch": current_branch,
            "git_head": current_head[:8] if current_head else "",
            "git_dirty": git_dirty,
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
                "cloud_repo_name": sync_state.cloud_repo_name or cloud_repo_name,
                "files_found": sync_state.files_found,
                "files_selected": sync_state.files_selected,
                "file_limit": sync_state.file_limit,
                "files_truncated": sync_state.files_truncated,
            }

        # Try to find cloud repo in list
        cloud_info = None
        warnings: list[str] = []
        try:
            repos = client.list_repos(trace_id=trace_id)
            if sync_state and sync_state.repo_id:
                target_id = sync_state.repo_id
                for repo in repos:
                    rid = repo.get("repo_id") or repo.get("id")
                    if rid == target_id:
                        cloud_info = {
                            "repo_id": rid,
                            "name": (repo.get("metadata") or {}).get("name") or repo.get("name"),
                            "auto_index": repo.get("auto_index"),
                            "created_at": repo.get("created_at"),
                            "updated_at": repo.get("updated_at"),
                        }
                        break
                if cloud_info is None:
                    warnings.append(
                        f"Synced repo_id '{target_id}' not found in cloud list; repo may be deleted or inaccessible."
                    )
            else:
                matches = []
                for repo in repos:
                    metadata = repo.get("metadata") or {}
                    name = metadata.get("name") or repo.get("name")
                    if name == cloud_repo_name:
                        matches.append(repo)
                if len(matches) == 1:
                    repo = matches[0]
                    cloud_info = {
                        "repo_id": repo.get("repo_id") or repo.get("id"),
                        "name": (repo.get("metadata") or {}).get("name") or repo.get("name"),
                        "auto_index": repo.get("auto_index"),
                        "created_at": repo.get("created_at"),
                        "updated_at": repo.get("updated_at"),
                    }
                elif len(matches) > 1:
                    warnings.append(
                        f"Multiple cloud repos found with name '{cloud_repo_name}'; cannot pick unambiguously."
                    )
        except Exception as exc:
            logger.warning("[%s] Failed to fetch cloud repos: %s", trace_id, exc)
            warnings.append(f"Failed to fetch cloud repo list: {exc}")

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
            elif git_dirty:
                needs_sync = True
                recommended_action = "Local working tree is dirty. Run cloud_sync() if you want cloud_search to reflect uncommitted changes."
        elif not sync_state:
            needs_sync = True
            recommended_action = "No sync state found. Run cloud_sync() to upload codebase."

        status_info = {
            "ref_changed": ref_changed,
            "needs_sync": needs_sync,
            "recommended_action": recommended_action,
        }

        if sync_state:
            if sync_state.files_truncated:
                warnings.append(
                    f"Last sync was limited to {sync_state.files_selected}/{sync_state.files_found} files "
                    f"(REPO_SYNC_MAX_FILES={sync_state.file_limit}); cloud search may be incomplete."
                )
            if sync_state.skipped_files:
                warnings.append(
                    f"Last sync skipped {len(sync_state.skipped_files)} files (binary/oversize/unreadable); "
                    "cloud search may miss those files."
                )
            if git_dirty:
                warnings.append("Local git working tree has uncommitted changes.")

        logger.debug(
            "[%s] Info retrieved: synced=%s, cloud=%s, ref_changed=%s",
            trace_id,
            synced_info is not None,
            cloud_info is not None,
            ref_changed,
        )

        result_payload = {
            "trace_id": trace_id,
            "repo_name": local_repo_name,
            "cloud_repo_name": cloud_repo_name,
            "local": local_info,
            "synced": synced_info,
            "cloud": cloud_info,
            "status": status_info,
            "warnings": warnings,
        }
        log_cloud_event(
            "cloud_info_complete",
            trace_id,
            repo_name=local_repo_name,
            cloud_repo_name=cloud_repo_name,
        )
        return result_payload

    except Exception as exc:
        logger.error("[%s] Cloud info failed: %s", trace_id, exc)
        result = {
            "trace_id": trace_id,
            "repo_name": local_repo_name,
            "cloud_repo_name": cloud_repo_name,
            "local": None,
            "synced": None,
            "cloud": None,
            "status": None,
            "error": str(exc),
            **build_cloud_error_details(exc),
        }
        log_cloud_event(
            "cloud_info_error",
            trace_id,
            repo_name=local_repo_name or None,
            cloud_repo_name=cloud_repo_name or None,
            **_extract_error_fields(result),
        )
        return result
