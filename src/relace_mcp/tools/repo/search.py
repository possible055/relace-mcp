import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient

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
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    query_preview = query[:100] if len(query) <= 100 else query[:97] + "..."
    logger.info("[%s] Starting cloud semantic search: %s", trace_id, query_preview)
    if branch:
        logger.info("[%s] Searching branch: %s", trace_id, branch)

    try:
        # Get or create repo based on base_dir name
        repo_name = client.get_repo_name_from_base_dir(base_dir)
        repo_id = client.ensure_repo(repo_name, trace_id=trace_id)

        # Execute semantic retrieval
        result = client.retrieve(
            repo_id=repo_id,
            query=query,
            branch=branch,  # Empty string = use API default
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
            "results": results,
            "repo_id": repo_id,
            "result_count": len(results),
        }

    except Exception as exc:
        logger.error("[%s] Cloud search failed: %s", trace_id, exc)
        return {
            "query": query,
            "branch": branch,
            "results": [],
            "repo_id": None,
            "error": str(exc),
        }
