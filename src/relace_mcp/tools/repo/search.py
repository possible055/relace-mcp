import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from .state import get_current_git_info, get_repo_identity, load_sync_state

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
    query_preview = query[:100] if len(query) <= 100 else query[:97] + "..."
    logger.info("[%s] Starting cloud semantic search: %s", trace_id, query_preview)
    if branch:
        logger.info("[%s] Searching branch: %s", trace_id, branch)

    try:
        local_repo_name, cloud_repo_name, _project_fingerprint = get_repo_identity(base_dir)
        if not local_repo_name or not cloud_repo_name:
            return {
                "query": query,
                "branch": branch,
                "results": [],
                "repo_id": None,
                "hash": "",
                "error": "Invalid base_dir: cannot derive repository name.",
            }

        # Read repo_id from sync state (requires prior cloud_sync)
        cached_state = load_sync_state(base_dir)

        if cached_state and cached_state.repo_id:
            repo_id = cached_state.repo_id
            git_head = cached_state.git_head_sha or ""
            logger.info(
                "[%s] Using cached repo_id=%s, git_head=%s",
                trace_id,
                repo_id[:8],
                git_head[:8] if git_head else "none",
            )
        else:
            logger.warning("[%s] No sync state found for '%s'", trace_id, local_repo_name)
            return {
                "query": query,
                "branch": branch,
                "results": [],
                "repo_id": None,
                "hash": "",
                "error": f"No sync state found for '{local_repo_name}'. Run cloud_sync first.",
            }

        warnings: list[str] = []
        current_branch, current_head = get_current_git_info(base_dir)
        if current_head and git_head and current_head != git_head:
            warnings.append(
                f"Local git HEAD ({current_head[:8]}) differs from last synced HEAD ({git_head[:8]}). "
                "Results reflect the last synced revision; run cloud_sync to update."
            )
        if not git_head:
            warnings.append(
                "Sync state is missing git_head_sha; search is not pinned to a specific commit."
            )

        # Execute semantic retrieval with commit hash
        result = client.retrieve(
            repo_id=repo_id,
            query=query,
            branch=branch,
            hash=git_head,
            score_threshold=score_threshold,
            token_limit=token_limit,
            include_content=True,
            trace_id=trace_id,
        )

        # Format results
        results = result.get("results", [])
        logger.info(
            "[%s] Cloud search completed, found %d results",
            trace_id,
            len(results),
        )

        return {
            "query": query,
            "branch": branch,
            "hash": git_head,
            "results": results,
            "repo_id": repo_id,
            "result_count": len(results),
            "repo_name": local_repo_name,
            "cloud_repo_name": cached_state.cloud_repo_name or cloud_repo_name,
            "warnings": warnings,
        }

    except Exception as exc:
        logger.error("[%s] Cloud search failed: %s", trace_id, exc)
        return {
            "query": query,
            "branch": branch,
            "hash": "",
            "results": [],
            "repo_id": None,
            "error": str(exc),
        }
