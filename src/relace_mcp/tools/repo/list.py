import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient

logger = logging.getLogger(__name__)


def cloud_list_logic(client: RelaceRepoClient) -> dict[str, Any]:
    """List all repositories in the Relace Cloud account.

    Args:
        client: RelaceRepoClient instance.

    Returns:
        Dict containing:
        - count: Number of repos returned
        - repos: List of repo summaries (repo_id, name, auto_index)
        - has_more: Whether there are more repos (page_size=100 limit)
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Listing cloud repositories", trace_id)

    try:
        repos = client.list_repos(trace_id=trace_id)

        # Extract relevant fields from each repo
        repo_summaries = []
        for repo in repos:
            metadata = repo.get("metadata") or {}
            repo_summaries.append(
                {
                    "repo_id": repo.get("repo_id") or repo.get("id"),
                    "name": metadata.get("name") or repo.get("name"),
                    "auto_index": repo.get("auto_index"),
                    "created_at": repo.get("created_at"),
                    "updated_at": repo.get("updated_at"),
                }
            )

        # Note: client.list_repos uses page_size=100, so has_more indicates truncation
        has_more = len(repos) >= 100

        logger.info("[%s] Found %d repositories", trace_id, len(repo_summaries))

        return {
            "count": len(repo_summaries),
            "repos": repo_summaries,
            "has_more": has_more,
        }

    except Exception as exc:
        logger.error("[%s] Cloud list failed: %s", trace_id, exc)
        return {
            "count": 0,
            "repos": [],
            "has_more": False,
            "error": str(exc),
        }
