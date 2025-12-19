import logging
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..config import (
    MAX_RETRIES,
    RELACE_API_ENDPOINT,
    RELACE_REPO_ID,
    REPO_SYNC_TIMEOUT_SECONDS,
    RETRY_BASE_DELAY,
    RelaceConfig,
)
from .exceptions import RelaceAPIError, raise_for_status

logger = logging.getLogger(__name__)


class RelaceRepoClient:
    """Client for Relace Repos API (api.relace.run).

    Provides source control operations (list, create, upload) and
    semantic retrieval for cloud-based code search.
    """

    def __init__(self, config: RelaceConfig) -> None:
        self._config = config
        self._base_url = RELACE_API_ENDPOINT.rstrip("/")
        self._cached_repo_id: str | None = RELACE_REPO_ID

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
        """List all repositories under the account.

        Returns:
            List of repo objects with id, name, etc.
        """
        url = f"{self._base_url}/repo"
        resp = self._request_with_retry(
            "GET",
            url,
            trace_id=trace_id,
            headers=self._get_headers(),
            params={"page_size": 100},
        )
        data = resp.json()
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return items
        return data if isinstance(data, list) else []

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
        return resp.json()

    def upload_file(
        self,
        repo_id: str,
        file_path: str,
        content: bytes,
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Upload a single file to the repository.

        Args:
            repo_id: Repository UUID.
            file_path: File path within the repo (e.g., "src/main.py").
            content: File content as bytes.
            trace_id: Trace ID for logging.

        Returns:
            Upload result from API.
        """
        # Normalize path separators (Windows backslash to forward slash)
        normalized_path = file_path.replace("\\", "/")
        # URL-encode the entire path (safe="" to encode slashes too)
        encoded_path = quote(normalized_path, safe="")
        url = f"{self._base_url}/repo/{repo_id}/file/{encoded_path}"
        resp = self._request_with_retry(
            "PUT",
            url,
            trace_id=trace_id,
            timeout=REPO_SYNC_TIMEOUT_SECONDS,
            headers=self._get_headers("application/octet-stream"),
            content=content,
        )
        # API returns 201 Created with JSON body containing repo_id, repo_head, changed_files
        # Also handle 204 No Content for backward compatibility
        if resp.status_code in (200, 201):
            try:
                return resp.json()
            except ValueError:
                return {"status": "ok", "path": file_path}
        if resp.status_code == 204:
            return {"status": "ok", "path": file_path}
        try:
            return resp.json()
        except ValueError:
            return {"status": "ok", "path": file_path}

    def ensure_repo(self, name: str, trace_id: str = "unknown") -> str:
        """Ensure a repository exists, creating if necessary.

        Args:
            name: Repository name.
            trace_id: Trace ID for logging.

        Returns:
            Repository ID (UUID).
        """
        # Use cached repo ID if available
        if self._cached_repo_id:
            return self._cached_repo_id

        # Search existing repos
        repos = self.list_repos(trace_id=trace_id)
        for repo in repos:
            metadata = repo.get("metadata")
            repo_name = metadata.get("name") if isinstance(metadata, dict) else repo.get("name")
            if repo_name == name:
                repo_id = repo.get("repo_id", repo.get("id", ""))
                if repo_id:
                    self._cached_repo_id = repo_id
                    if repo.get("auto_index") is False:
                        logger.warning(
                            "[%s] Repo '%s' has auto_index=false; semantic retrieval may not work",
                            trace_id,
                            name,
                        )
                    logger.info("[%s] Found existing repo '%s' with id=%s", trace_id, name, repo_id)
                    return repo_id

        # Create new repo
        logger.info("[%s] Creating new repo '%s'", trace_id, name)
        result = self.create_repo(name, trace_id=trace_id)
        repo_id = result.get("repo_id", result.get("id", ""))
        if not repo_id:
            raise RuntimeError(f"Failed to create repo: {result}")
        self._cached_repo_id = repo_id
        return repo_id

    def delete_repo(self, repo_id: str, trace_id: str = "unknown") -> bool:
        """Delete a repository.

        Args:
            repo_id: Repository UUID.
            trace_id: Trace ID for logging.

        Returns:
            True if deleted successfully.
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
            return True
        except RuntimeError as exc:
            logger.error("[%s] Failed to delete repo '%s': %s", trace_id, repo_id, exc)
            return False

    # === Semantic Retrieval ===

    def retrieve(
        self,
        repo_id: str,
        query: str,
        branch: str = "main",
        score_threshold: float = 0.3,
        token_limit: int = 30000,
        include_content: bool = True,
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Perform semantic search over the repository.

        Args:
            repo_id: Repository UUID.
            query: Natural language search query.
            branch: Branch to search (default: "main").
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
        return resp.json()

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
        return resp.json()

    def get_repo_name_from_base_dir(self) -> str:
        """Derive repository name from base_dir."""
        return Path(self._config.base_dir).name
