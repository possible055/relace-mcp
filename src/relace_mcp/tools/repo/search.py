import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from .errors import build_cloud_error_details
from .logging import log_cloud_search_complete, log_cloud_search_error, log_cloud_search_start
from .state import get_current_git_info, get_repo_identity, is_git_dirty, load_sync_state

logger = logging.getLogger(__name__)


def cloud_search_logic(
    client: RelaceRepoClient,
    base_dir: str,
    query: str,
    branch: str = "",
    score_threshold: float = 0.3,
    token_limit: int = 30000,
) -> dict[str, Any]:
    """Execute semantic search over the cloud-synced codebase.

    Args:
        client: RelaceRepoClient instance.
        query: Natural language search query.
        branch: Branch to search (empty string uses API default branch).
        score_threshold: Minimum relevance score (0.0-1.0).
        token_limit: Maximum tokens to return in results.

    Returns:
        Dict containing:
        - query: Original query
        - branch: Branch searched (empty if using default)
        - results: List of matching files with content
        - repo_id: Repository ID used
        - hash: Commit SHA used for search (if available)
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Starting cloud semantic search", trace_id)

    local_repo_name: str | None = None
    cloud_repo_name: str | None = None

    try:
        local_repo_name, cloud_repo_name, _project_fingerprint = get_repo_identity(base_dir)
        if not local_repo_name or not cloud_repo_name:
            error_result: dict[str, Any] = {
                "trace_id": trace_id,
                "query": query,
                "branch": branch,
                "results": [],
                "repo_id": None,
                "hash": "",
                "error": "Invalid base_dir: cannot derive repository name.",
            }
            log_cloud_search_error(trace_id, None, None, error_result)
            return error_result

        log_cloud_search_start(
            trace_id,
            local_repo_name,
            cloud_repo_name,
            query,
            branch,
            score_threshold,
            token_limit,
        )

        # Read repo_id from sync state (requires prior cloud_sync)
        cached_state = load_sync_state(base_dir)

        if cached_state and cached_state.repo_id:
            repo_id = cached_state.repo_id
            git_head = cached_state.git_head_sha or ""
            logger.info("[%s] Using cached repo state", trace_id)
        else:
            logger.warning("[%s] No sync state found for repository", trace_id)
            no_sync_result: dict[str, Any] = {
                "trace_id": trace_id,
                "query": query,
                "branch": branch,
                "results": [],
                "repo_id": None,
                "hash": "",
                "repo_name": local_repo_name,
                "cloud_repo_name": cloud_repo_name,
                "error": f"No sync state found for '{local_repo_name}'. Run cloud_sync first.",
            }
            log_cloud_search_error(trace_id, local_repo_name, cloud_repo_name, no_sync_result)
            return no_sync_result

        warnings_list: list[str] = []
        current_branch, current_head = get_current_git_info(base_dir)
        if current_head and git_head and current_head != git_head:
            warnings_list.append(
                f"Local git HEAD ({current_head[:8]}) differs from last synced HEAD ({git_head[:8]}). "
                "Results reflect the last synced revision; run cloud_sync to update."
            )
        if not git_head:
            warnings_list.append(
                "Sync state is missing git_head_sha; search is not pinned to a specific commit."
            )
        if is_git_dirty(base_dir):
            warnings_list.append(
                "Local git working tree has uncommitted changes; results reflect the last synced revision."
            )
        if cached_state.files_truncated:
            warnings_list.append(
                f"Last sync was limited to {cached_state.files_selected}/{cached_state.files_found} files "
                f"(REPO_SYNC_MAX_FILES={cached_state.file_limit}); results may be incomplete."
            )
        if cached_state.skipped_files:
            warnings_list.append(
                f"Last sync skipped {len(cached_state.skipped_files)} files (binary/oversize/unreadable); "
                "results may miss those files."
            )

        # Determine whether to use cached hash for search
        # Only use hash when: (1) no branch specified, or (2) branch matches sync state
        # This prevents ignoring user's branch selection when API prioritizes hash over branch
        use_cached_hash = (not branch) or (branch == cached_state.git_branch)
        hash_to_send = git_head if use_cached_hash else ""

        if branch and not use_cached_hash:
            warnings_list.append(
                f"Searching branch '{branch}' without commit pinning (differs from synced branch "
                f"'{cached_state.git_branch}'). Results reflect the latest indexed state of '{branch}'."
            )

        # Execute semantic retrieval with commit hash
        result = client.retrieve(
            repo_id=repo_id,
            query=query,
            branch=branch,
            hash=hash_to_send,
            score_threshold=score_threshold,
            token_limit=token_limit,
            include_content=True,
            trace_id=trace_id,
        )

        # Format results
        raw_results = result.get("results")
        results: list[Any] = raw_results if isinstance(raw_results, list) else []
        logger.info(
            "[%s] Cloud search completed, found %d results",
            trace_id,
            len(results),
        )

        result_payload = {
            "trace_id": trace_id,
            "query": query,
            "branch": branch,
            "hash": hash_to_send,
            "results": results,
            "repo_id": repo_id,
            "result_count": len(results),
            "repo_name": local_repo_name,
            "cloud_repo_name": cached_state.cloud_repo_name or cloud_repo_name,
            "warnings": warnings_list,
        }
        log_cloud_search_complete(trace_id, result_payload)
        return result_payload

    except Exception as exc:
        logger.error("[%s] Cloud search failed: %s", trace_id, exc)
        exc_result: dict[str, Any] = {
            "trace_id": trace_id,
            "query": query,
            "branch": branch,
            "hash": "",
            "results": [],
            "repo_id": None,
            "error": str(exc),
            **build_cloud_error_details(exc),
        }
        if local_repo_name and cloud_repo_name:
            exc_result["repo_name"] = local_repo_name
            exc_result["cloud_repo_name"] = cloud_repo_name
        log_cloud_search_error(trace_id, local_repo_name, cloud_repo_name, exc_result)
        return exc_result
