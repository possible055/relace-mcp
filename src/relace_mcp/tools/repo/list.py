import logging
import uuid
from typing import Any

import httpx

from ...clients.exceptions import RelaceAPIError
from ...clients.repo import RelaceRepoClient

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

        # list_repos uses automatic pagination with a safety limit of 100 pages.
        # has_more is true only if we hit the safety limit (100 * 100 = 10,000 repos).
        # Note: This may be a false positive if total is exactly 10,000.
        has_more = len(repos) >= 10000

        logger.info("[%s] Found %d repositories", trace_id, len(repo_summaries))

        return {
            "count": len(repo_summaries),
            "repos": repo_summaries,
            "has_more": has_more,
        }

    except Exception as exc:
        logger.error("[%s] Cloud list failed: %s", trace_id, exc)
        error_details: dict[str, Any] = {}
        cause = exc.__cause__
        if isinstance(cause, RelaceAPIError):
            error_details = {
                "status_code": cause.status_code,
                "error_code": cause.code,
                "retryable": cause.retryable,
            }
            if cause.status_code in {401, 403}:
                error_details["recommended_action"] = "Check RELACE_API_KEY and retry."
            elif cause.status_code == 429:
                error_details["recommended_action"] = "Rate limited. Retry later."
        elif isinstance(cause, httpx.TimeoutException):
            error_details = {
                "error_code": "timeout",
                "retryable": True,
                "recommended_action": "Check network connectivity and retry.",
            }
        elif isinstance(cause, httpx.RequestError):
            error_details = {
                "error_code": "network_error",
                "retryable": True,
                "recommended_action": "Check network connectivity, DNS/proxy, and RELACE_API_ENDPOINT.",
            }
        return {
            "count": 0,
            "repos": [],
            "has_more": False,
            "error": str(exc),
            **error_details,
        }
