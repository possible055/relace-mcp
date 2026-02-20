import logging
import uuid
from typing import Any

from ...clients.repo import RelaceRepoClient
from ..core import build_cloud_error_details, extract_error_fields, log_cloud_event

logger = logging.getLogger(__name__)


def cloud_list_logic(client: RelaceRepoClient) -> dict[str, Any]:
    """List all repositories in the Relace Cloud account.

    Uses automatic pagination to fetch all repos (up to 10,000 safety limit).

    Args:
        client: RelaceRepoClient instance.

    Returns:
        Dict containing:
        - count: Number of repos returned
        - repos: List of repo summaries (repo_id, name, auto_index)
        - has_more: True only if safety limit (10,000 repos) was reached
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.debug("[%s] Listing cloud repositories", trace_id)

    try:
        log_cloud_event("cloud_list_start", trace_id)
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

        # list_repos uses automatic pagination with a safety limit of 100 pages.
        # has_more is true only if we hit the safety limit (100 * 100 = 10,000 repos).
        # Note: This may be a false positive if total is exactly 10,000.
        has_more = len(repos) >= 10000

        logger.debug("[%s] Found %d repositories", trace_id, len(repo_summaries))

        result = {
            "trace_id": trace_id,
            "count": len(repo_summaries),
            "repos": repo_summaries,
            "has_more": has_more,
        }
        log_cloud_event("cloud_list_complete", trace_id, count=len(repo_summaries))
        return result

    except Exception as exc:
        logger.error("[%s] Cloud list failed: %s", trace_id, exc)
        result = {
            "trace_id": trace_id,
            "count": 0,
            "repos": [],
            "has_more": False,
            "error": str(exc),
            **build_cloud_error_details(exc),
        }
        log_cloud_event("cloud_list_error", trace_id, **extract_error_fields(result))
        return result
