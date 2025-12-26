"""Tests for RelaceRepoClient."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients.exceptions import RelaceAPIError
from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.config import RelaceConfig


@pytest.fixture
def mock_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(
        api_key="rlc-test-api-key-12345",
        base_dir=str(tmp_path),
    )


@pytest.fixture
def repo_client(mock_config: RelaceConfig) -> RelaceRepoClient:
    return RelaceRepoClient(mock_config)


class TestRelaceRepoClientInit:
    """Test RelaceRepoClient initialization."""

    def test_init_with_config(self, mock_config: RelaceConfig) -> None:
        """Should initialize with config."""
        client = RelaceRepoClient(mock_config)
        assert client._config == mock_config
        assert "api.relace.run" in client._base_url

    def test_get_repo_name_from_base_dir(self, mock_config: RelaceConfig) -> None:
        """Should derive repo name from base_dir."""
        client = RelaceRepoClient(mock_config)
        repo_name = client.get_repo_name_from_base_dir()
        # tmp_path typically has a random name like pytest-xxx
        assert repo_name == Path(mock_config.base_dir).name


class TestRelaceRepoClientListRepos:
    """Test list_repos method."""

    def test_list_repos_returns_list(self, repo_client: RelaceRepoClient) -> None:
        """Should return list of repos."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "items": [
                {"repo_id": "repo-1", "metadata": {"name": "test-repo"}},
                {"repo_id": "repo-2", "metadata": {"name": "another-repo"}},
            ]
        }

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            repos = repo_client.list_repos()

        assert len(repos) == 2
        assert repos[0]["metadata"]["name"] == "test-repo"

    def test_list_repos_handles_direct_list_response(self, repo_client: RelaceRepoClient) -> None:
        """Should handle API returning list directly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = [
            {"id": "repo-1", "name": "test-repo"},
        ]

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            repos = repo_client.list_repos()

        assert len(repos) == 1

    def test_list_repos_paginates_multiple_pages(self, repo_client: RelaceRepoClient) -> None:
        """Should fetch all pages using page_start/next_page cursor pagination."""
        # Page 1: 100 items with next_page cursor
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.is_success = True
        page1_response.json.return_value = {
            "items": [{"repo_id": f"repo-{i}"} for i in range(100)],
            "next_page": 100,  # Cursor to next page
            "total_items": 150,
        }

        # Page 2: 50 items, no next_page = last page
        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.is_success = True
        page2_response.json.return_value = {
            "items": [{"repo_id": f"repo-{i}"} for i in range(100, 150)],
            # No next_page = last page
            "total_items": 150,
        }

        with patch.object(
            repo_client, "_request_with_retry", side_effect=[page1_response, page2_response]
        ) as mock_request:
            repos = repo_client.list_repos()

        assert len(repos) == 150
        assert mock_request.call_count == 2
        # Verify page_start parameter usage
        call_args_list = mock_request.call_args_list
        # First call: no page_start (or page_start=0)
        assert call_args_list[0].kwargs["params"].get("page_start", 0) == 0
        # Second call: page_start=100 (from next_page)
        assert call_args_list[1].kwargs["params"]["page_start"] == 100

    def test_list_repos_stops_when_no_next_page(self, repo_client: RelaceRepoClient) -> None:
        """Should stop pagination when next_page is omitted (no more pages)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "items": [{"repo_id": "repo-1"}],
            # No next_page = only one page
            "total_items": 1,
        }

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            repos = repo_client.list_repos()

        assert len(repos) == 1

    def test_list_repos_stops_on_empty_page(self, repo_client: RelaceRepoClient) -> None:
        """Should stop pagination when receiving empty response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"items": [], "total_items": 0}

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            repos = repo_client.list_repos()

        assert len(repos) == 0

    def test_list_repos_respects_page_limit(self, repo_client: RelaceRepoClient) -> None:
        """Should stop at 100 pages safety limit to prevent infinite loops."""
        call_count = 0

        def mock_paginated_response(*args, **kwargs):
            nonlocal call_count
            page_start = kwargs.get("params", {}).get("page_start", 0)
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.is_success = True
            mock_resp.json.return_value = {
                "items": [{"repo_id": f"repo-{page_start + i}"} for i in range(100)],
                "next_page": page_start + 100,  # Always return next_page
                "total_items": 999999,  # Pretend there are many repos
            }
            return mock_resp

        with patch.object(repo_client, "_request_with_retry", side_effect=mock_paginated_response):
            repos = repo_client.list_repos()

        # Should stop at 100 pages = 10,000 repos
        assert len(repos) == 10000
        assert call_count == 100


class TestRelaceRepoClientCreateRepo:
    """Test create_repo method."""

    def test_create_repo_basic(self, repo_client: RelaceRepoClient) -> None:
        """Should create repo with basic metadata."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.is_success = True
        mock_response.json.return_value = {
            "repo_id": "new-repo-id",
            "repo_head": "abc123",
        }

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            result = repo_client.create_repo(name="test-repo", auto_index=True)

            call_args = mock_request.call_args
            payload = call_args.kwargs.get("json")
            assert payload is not None
            assert payload["metadata"]["name"] == "test-repo"
            assert payload["auto_index"] is True
            assert "source" not in payload

        assert result["repo_id"] == "new-repo-id"

    def test_create_repo_with_source_files(self, repo_client: RelaceRepoClient) -> None:
        """Should create repo with source files."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.is_success = True
        mock_response.json.return_value = {
            "repo_id": "new-repo-id",
            "repo_head": "abc123",
        }

        source = {
            "type": "files",
            "files": [
                {"filename": "src/main.py", "content": "print('hello')"},
            ],
        }

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            result = repo_client.create_repo(name="test-repo", auto_index=True, source=source)

            call_args = mock_request.call_args
            payload = call_args.kwargs.get("json")
            assert payload is not None
            assert payload["source"] == source
            assert payload["source"]["type"] == "files"
            assert len(payload["source"]["files"]) == 1

        assert result["repo_id"] == "new-repo-id"

    def test_create_repo_with_source_git(self, repo_client: RelaceRepoClient) -> None:
        """Should create repo from git URL."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.is_success = True
        mock_response.json.return_value = {
            "repo_id": "new-repo-id",
            "repo_head": "abc123",
        }

        source = {
            "type": "git",
            "url": "https://github.com/example/repo.git",
            "branch": "main",
        }

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            result = repo_client.create_repo(name="cloned-repo", auto_index=False, source=source)

            call_args = mock_request.call_args
            payload = call_args.kwargs.get("json")
            assert payload is not None
            assert payload["source"]["type"] == "git"
            assert payload["source"]["url"] == "https://github.com/example/repo.git"
            assert payload["auto_index"] is False

        assert result["repo_id"] == "new-repo-id"


class TestRelaceRepoClientEnsureRepo:
    """Test ensure_repo method."""

    def test_ensure_repo_uses_cached_id(self, mock_config: RelaceConfig) -> None:
        """Should return cached repo_id if available."""
        with patch("relace_mcp.clients.repo.RELACE_REPO_ID", "cached-repo-id"):
            client = RelaceRepoClient(mock_config)
            repo_id = client.ensure_repo("test-repo")

        assert repo_id == "cached-repo-id"

    def test_ensure_repo_finds_existing(self, repo_client: RelaceRepoClient) -> None:
        """Should find and return existing repo."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "items": [
                {"repo_id": "existing-repo-id", "metadata": {"name": "test-repo"}},
            ]
        }

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            repo_id = repo_client.ensure_repo("test-repo")

        assert repo_id == "existing-repo-id"

    def test_ensure_repo_creates_new(self, repo_client: RelaceRepoClient) -> None:
        """Should create new repo if not found."""
        list_response = MagicMock()
        list_response.status_code = 200
        list_response.is_success = True
        list_response.json.return_value = {"items": []}

        create_response = MagicMock()
        create_response.status_code = 201
        create_response.is_success = True
        create_response.json.return_value = {"repo_id": "new-repo-id"}

        with patch.object(
            repo_client, "_request_with_retry", side_effect=[list_response, create_response]
        ):
            repo_id = repo_client.ensure_repo("test-repo")

        assert repo_id == "new-repo-id"

    def test_ensure_repo_caches_per_name(self, repo_client: RelaceRepoClient) -> None:
        """Should cache repo IDs per repo name (not globally)."""
        with patch.object(
            repo_client,
            "list_repos",
            side_effect=[
                [{"repo_id": "id-a", "metadata": {"name": "repo-a"}}],
                [{"repo_id": "id-b", "metadata": {"name": "repo-b"}}],
            ],
        ) as mock_list:
            repo_id_a = repo_client.ensure_repo("repo-a")
            repo_id_b = repo_client.ensure_repo("repo-b")
            repo_id_a_again = repo_client.ensure_repo("repo-a")

        assert repo_id_a == "id-a"
        assert repo_id_b == "id-b"
        assert repo_id_a_again == "id-a"
        assert mock_list.call_count == 2


class TestRelaceRepoClientRetrieve:
    """Test retrieve (semantic search) method."""

    def test_retrieve_sends_correct_payload(self, repo_client: RelaceRepoClient) -> None:
        """Should send correct payload for semantic search."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "results": [
                {"filename": "src/auth.py", "content": "def login(): ..."},
            ]
        }

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            result = repo_client.retrieve(
                repo_id="test-repo-id",
                query="user authentication",
                score_threshold=0.5,
                token_limit=10000,
            )

            # Verify payload
            call_args = mock_request.call_args
            payload = call_args.kwargs.get("json")
            assert payload is not None
            assert payload["query"] == "user authentication"
            assert payload["score_threshold"] == 0.5
            assert payload["token_limit"] == 10000
            assert payload["include_content"] is True

        assert len(result["results"]) == 1


class TestRelaceRepoClientRetry:
    """Test retry behavior."""

    def test_retries_on_429(self, repo_client: RelaceRepoClient) -> None:
        """Should retry on rate limit (429) error."""
        call_count = 0

        def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                mock_resp = MagicMock()
                mock_resp.status_code = 429
                mock_resp.is_success = False
                mock_resp.text = '{"code": "rate_limit", "message": "Too many requests"}'
                mock_resp.headers = {"retry-after": "0.1"}
                return mock_resp
            else:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.is_success = True
                mock_resp.json.return_value = {"items": []}
                return mock_resp

        with patch("relace_mcp.clients.repo.httpx.Client") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.__exit__.return_value = None
            mock_instance.request = MagicMock(side_effect=mock_request)
            mock_client_class.return_value = mock_instance

            with patch("relace_mcp.clients.repo.time.sleep"):
                repos = repo_client.list_repos()

        assert call_count == 3
        assert repos == []

    def test_raises_on_non_retryable_error(self, repo_client: RelaceRepoClient) -> None:
        """Should raise immediately on non-retryable error (401)."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.is_success = False
        mock_response.text = '{"code": "invalid_api_key", "message": "Invalid API key"}'
        mock_response.headers = {}

        with patch("relace_mcp.clients.repo.httpx.Client") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.__exit__.return_value = None
            mock_instance.request = MagicMock(return_value=mock_response)
            mock_client_class.return_value = mock_instance

            with pytest.raises(RuntimeError, match="invalid_api_key"):
                repo_client.list_repos()


class TestRelaceRepoClientDeleteRepo:
    """Test delete_repo behavior."""

    def test_delete_repo_treats_404_as_success(self, repo_client: RelaceRepoClient) -> None:
        """Should treat 404 as idempotent success and clear cached repo_id."""
        repo_client._cached_repo_ids["test-repo"] = "test-repo-id"

        api_error = RelaceAPIError(
            status_code=404,
            code="not_found",
            message="Repo not found",
            retryable=False,
        )

        def raise_not_found(*args, **kwargs):
            raise RuntimeError("Repos API error (not_found): Repo not found") from api_error

        with patch.object(repo_client, "_request_with_retry", side_effect=raise_not_found):
            assert repo_client.delete_repo("test-repo-id") is True

        assert "test-repo" not in repo_client._cached_repo_ids

    def test_delete_repo_returns_false_on_other_errors(self, repo_client: RelaceRepoClient) -> None:
        """Should return False for non-404 API errors."""
        repo_client._cached_repo_ids["test-repo"] = "test-repo-id"

        api_error = RelaceAPIError(
            status_code=403,
            code="forbidden",
            message="Forbidden",
            retryable=False,
        )

        def raise_forbidden(*args, **kwargs):
            raise RuntimeError("Repos API error (forbidden): Forbidden") from api_error

        with patch.object(repo_client, "_request_with_retry", side_effect=raise_forbidden):
            assert repo_client.delete_repo("test-repo-id") is False

        # Cached ID should remain unchanged on failure
        assert repo_client._cached_repo_ids["test-repo"] == "test-repo-id"
