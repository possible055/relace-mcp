import logging
import os
import random
import time
from pathlib import Path
from typing import Any, cast

import httpx

from ..config import RelaceConfig
from ..config.settings import (
    MAX_RETRIES,
    RELACE_API_ENDPOINT,
    RELACE_REPO_ID,
    REPO_SYNC_TIMEOUT_SECONDS,
    RETRY_BASE_DELAY,
)
from .exceptions import RelaceAPIError, raise_for_status

logger = logging.getLogger(__name__)

# Maximum repos to fetch (configurable via environment variable)
# Default: 10000 (100 pages * 100 per page)
REPO_LIST_MAX = int(os.getenv("RELACE_REPO_LIST_MAX", "10000"))


class RelaceRepoClient:
    """Client for Relace Repos API (api.relace.run).

    Provides source control operations (list, create, upload) and
    semantic retrieval for cloud-based code search.
    """

    def __init__(self, config: RelaceConfig) -> None:
        self._config = config
        self._base_url = RELACE_API_ENDPOINT.rstrip("/")
        self._forced_repo_id: str | None = RELACE_REPO_ID
        self._cached_repo_ids: dict[str, str] = {}

    def _get_headers(self, content_type: str = "application/json") -> dict[str, str]:
        """Build request headers with authorization."""
        return {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": content_type,
        }

    def _request_with_retry(
        self,
        method: str,
        url: str,
        trace_id: str = "unknown",
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            url: Full URL to request.
            trace_id: Trace ID for logging.
            timeout: Request timeout in seconds.
            **kwargs: Additional arguments for httpx request.

        Returns:
            httpx.Response object on success.

        Raises:
            RuntimeError: When request fails after all retries.
        """
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                started_at = time.monotonic()
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(method, url, **kwargs)
                latency_ms = int((time.monotonic() - started_at) * 1000)

                try:
                    raise_for_status(resp)
                except RelaceAPIError as exc:
                    if not exc.retryable:
                        logger.error(
                            "[%s] Repos API %s (status=%d, latency=%dms): %s",
                            trace_id,
                            exc.code,
                            resp.status_code,
                            latency_ms,
                            exc.message,
                        )
                        raise RuntimeError(f"Repos API error ({exc.code}): {exc.message}") from exc

                    last_exc = exc
                    logger.warning(
                        "[%s] Repos API %s (status=%d, latency=%dms, attempt=%d/%d)",
                        trace_id,
                        exc.code,
                        resp.status_code,
                        latency_ms,
                        attempt + 1,
                        MAX_RETRIES + 1,
                    )
                    if attempt < MAX_RETRIES:
                        delay = exc.retry_after or RETRY_BASE_DELAY * (2**attempt)
                        delay += random.uniform(0, 0.5)  # nosec B311
                        time.sleep(delay)
                        continue
                    raise RuntimeError(f"Repos API error ({exc.code}): {exc.message}") from exc

                logger.debug(
                    "[%s] Repos API success (status=%d, latency=%dms)",
                    trace_id,
                    resp.status_code,
                    latency_ms,
                )
                return resp

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "[%s] Repos API timeout after %.1fs (attempt=%d/%d)",
                    trace_id,
                    timeout,
                    attempt + 1,
                    MAX_RETRIES + 1,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Repos API request timed out after {timeout}s") from exc

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "[%s] Repos API network error: %s (attempt=%d/%d)",
                    trace_id,
                    exc,
                    attempt + 1,
                    MAX_RETRIES + 1,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Repos API network error: {exc}") from exc

        raise RuntimeError(
            f"Repos API request failed after {MAX_RETRIES + 1} attempts"
        ) from last_exc

    # === Source Control ===

    def list_repos(self, trace_id: str = "unknown") -> list[dict[str, Any]]:
        """List all repositories under the account with automatic pagination.

        Uses page_start/next_page cursor-based pagination per Relace API spec.
        Respects RELACE_REPO_LIST_MAX environment variable for resource limits.

        Returns:
            List of repo objects with id, name, etc.
        """
        url = f"{self._base_url}/repo"
        all_repos: list[dict[str, Any]] = []
        page_start: int | None = 0
        page_size = 100
        max_iterations = (REPO_LIST_MAX + page_size - 1) // page_size  # Ceiling division

        for _ in range(max_iterations):
            params: dict[str, Any] = {"page_size": page_size}
            if page_start is not None and page_start > 0:
                params["page_start"] = page_start

            resp = self._request_with_retry(
                "GET",
                url,
                trace_id=trace_id,
                headers=self._get_headers(),
                params=params,
            )
            data = resp.json()

            # Extract items from response
            items: list[dict[str, Any]] = []
            if isinstance(data, dict):
                items = data.get("items", [])
                if not isinstance(items, list):
                    items = []
                # Get next_page cursor from response (omitted if no more pages)
                page_start = data.get("next_page")
            elif isinstance(data, list):
                # Legacy: API returning list directly (no pagination info)
                items = data
                page_start = None

            all_repos.extend(items)

            # Stop if: reached limit, no next_page cursor, or empty response
            if len(all_repos) >= REPO_LIST_MAX:
                logger.warning(
                    "[%s] list_repos reached limit (%d repos), truncating results",
                    trace_id,
                    REPO_LIST_MAX,
                )
                all_repos = all_repos[:REPO_LIST_MAX]
                break
            if page_start is None or len(items) == 0:
                break
        else:
            logger.warning(
                "[%s] list_repos reached safety limit (%d pages), stopping pagination",
                trace_id,
                max_iterations,
            )

        return all_repos

    def create_repo(
        self,
        name: str,
        auto_index: bool = True,
        source: dict[str, Any] | None = None,
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Create a new repository.

        Args:
            name: Repository name.
            auto_index: Whether to enable indexing for semantic retrieval.
            source: Optional source to initialize repo from. Supports:
                - {"type": "files", "files": [{"filename": "...", "content": "..."}]}
                - {"type": "git", "url": "...", "branch": "..."}
                - {"type": "relace", "repo_id": "..."}
            trace_id: Trace ID for logging.

        Returns:
            Created repo object with repo_id, repo_head, etc.
        """
        url = f"{self._base_url}/repo"
        payload: dict[str, Any] = {"metadata": {"name": name}, "auto_index": auto_index}
        if source is not None:
            payload["source"] = source
        resp = self._request_with_retry(
            "POST",
            url,
            trace_id=trace_id,
            headers=self._get_headers(),
            json=payload,
        )
        return cast(dict[str, Any], resp.json())

    def ensure_repo(self, name: str, trace_id: str = "unknown") -> str:
        """Ensure a repository exists, creating if necessary.

        Args:
            name: Repository name.
            trace_id: Trace ID for logging.

        Returns:
            Repository ID (UUID).
        """
        # Use forced repo ID if configured (ignore name)
        if self._forced_repo_id:
            return self._forced_repo_id

        # Use cached repo ID for this repo name if available
        cached = self._cached_repo_ids.get(name)
        if cached:
            return cached

        # Search existing repos
        repos = self.list_repos(trace_id=trace_id)
        for repo in repos:
            metadata = repo.get("metadata")
            repo_name = metadata.get("name") if isinstance(metadata, dict) else repo.get("name")
            if repo_name != name:
                continue

            repo_id = repo.get("repo_id") or repo.get("id") or ""
            if not repo_id:
                continue

            self._cached_repo_ids[name] = str(repo_id)

            if repo.get("auto_index") is False:
                logger.warning(
                    "[%s] Repo '%s' has auto_index=false; semantic retrieval may not work",
                    trace_id,
                    name,
                )

            logger.info("[%s] Found existing repo '%s' with id=%s", trace_id, name, repo_id)
            return str(repo_id)

        # Create new repo
        logger.info("[%s] Creating new repo '%s'", trace_id, name)
        result = self.create_repo(name, trace_id=trace_id)
        repo_id_val = result.get("repo_id") or result.get("id") or ""
        if not repo_id_val:
            raise RuntimeError(f"Failed to create repo: {result}")
        self._cached_repo_ids[name] = str(repo_id_val)
        return str(repo_id_val)

    def delete_repo(self, repo_id: str, trace_id: str = "unknown") -> bool:
        """Delete a repository.

        Args:
            repo_id: Repository UUID.
            trace_id: Trace ID for logging.

        Returns:
            True if deleted successfully or already deleted (idempotent).
        """
        url = f"{self._base_url}/repo/{repo_id}"
        try:
            self._request_with_retry(
                "DELETE",
                url,
                trace_id=trace_id,
                headers=self._get_headers(),
            )
            logger.info("[%s] Deleted repo '%s'", trace_id, repo_id)

            # Clear cached IDs if we just deleted them
            self._cached_repo_ids = {
                name: rid for name, rid in self._cached_repo_ids.items() if rid != repo_id
            }

            return True
        except RuntimeError as exc:
            # Treat 404 as success (repo already deleted - idempotent).
            # `_request_with_retry` wraps API errors in RuntimeError but preserves
            # the original `RelaceAPIError` as `__cause__`.
            cause = exc.__cause__
            if isinstance(cause, RelaceAPIError) and cause.status_code == 404:
                logger.info("[%s] Repo '%s' already deleted (404)", trace_id, repo_id)
                self._cached_repo_ids = {
                    name: rid for name, rid in self._cached_repo_ids.items() if rid != repo_id
                }
                return True
            logger.error("[%s] Failed to delete repo '%s': %s", trace_id, repo_id, exc)
            return False

    # === Semantic Retrieval ===

    def retrieve(
        self,
        repo_id: str,
        query: str,
        branch: str = "",
        score_threshold: float = 0.3,
        token_limit: int = 30000,
        include_content: bool = True,
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Perform semantic search over the repository.

        Args:
            repo_id: Repository UUID.
            query: Natural language search query.
            branch: Branch to search (empty string uses API default branch).
            score_threshold: Minimum relevance score (0.0-1.0).
            token_limit: Maximum tokens to return.
            include_content: Whether to include file content in results.
            trace_id: Trace ID for logging.

        Returns:
            Search results with matching files and content.
        """
        url = f"{self._base_url}/repo/{repo_id}/retrieve"
        payload: dict[str, Any] = {
            "query": query,
            "score_threshold": score_threshold,
            "token_limit": token_limit,
            "include_content": include_content,
        }
        if branch:
            payload["branch"] = branch
        resp = self._request_with_retry(
            "POST",
            url,
            trace_id=trace_id,
            headers=self._get_headers(),
            json=payload,
        )
        return cast(dict[str, Any], resp.json())

    def update_repo(
        self,
        repo_id: str,
        operations: list[dict[str, Any]],
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Update repo with diff operations (incremental sync).

        Args:
            repo_id: Repository UUID.
            operations: List of diff operations. Each operation is a dict with:
                - {"type": "write", "filename": "...", "content": "..."}
                - {"type": "rename", "old_filename": "...", "new_filename": "..."}
                - {"type": "delete", "filename": "..."}
            trace_id: Trace ID for logging.

        Returns:
            Dict containing repo_head and changed_files.
        """
        url = f"{self._base_url}/repo/{repo_id}/update"
        payload = {
            "source": {
                "type": "diff",
                "operations": operations,
            }
        }
        resp = self._request_with_retry(
            "POST",
            url,
            trace_id=trace_id,
            timeout=REPO_SYNC_TIMEOUT_SECONDS,
            headers=self._get_headers(),
            json=payload,
        )
        return cast(dict[str, Any], resp.json())

    def update_repo_files(
        self,
        repo_id: str,
        files: list[dict[str, str]],
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Update repo with complete file list (mirror sync).

        This uses type="files" to completely overwrite the repository content.
        Files not included in the list will be deleted from the cloud repo.

        Args:
            repo_id: Repository UUID.
            files: List of file dicts with:
                - {"filename": "path/to/file.py", "content": "..."}
            trace_id: Trace ID for logging.

        Returns:
            Dict containing repo_id and repo_head.
        """
        url = f"{self._base_url}/repo/{repo_id}/update"
        payload = {
            "source": {
                "type": "files",
                "files": files,
            }
        }
        resp = self._request_with_retry(
            "POST",
            url,
            trace_id=trace_id,
            timeout=REPO_SYNC_TIMEOUT_SECONDS,
            headers=self._get_headers(),
            json=payload,
        )
        return cast(dict[str, Any], resp.json())

    def get_repo_name_from_base_dir(self, base_dir: str | None = None) -> str:
        """Derive repository name from base_dir.

        Args:
            base_dir: Optional base_dir override (useful when base_dir is resolved dynamically
                from MCP Roots and not stored in config).
        """
        base_dir = base_dir or self._config.base_dir
        if base_dir is None:
            raise RuntimeError("base_dir is not configured")
        return Path(base_dir).name
