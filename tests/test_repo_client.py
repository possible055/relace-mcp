"""Tests for RelaceRepoClient."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


class TestRelaceRepoClientUploadFile:
    """Test upload_file method."""

    def test_upload_file_encodes_path_correctly(self, repo_client: RelaceRepoClient) -> None:
        """Should properly URL-encode file path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            repo_client.upload_file(
                repo_id="test-repo-id",
                file_path="src/main.py",
                content=b"print('hello')",
            )

            # Verify URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("url")
            assert "src%2Fmain.py" in url

    def test_upload_file_handles_windows_paths(self, repo_client: RelaceRepoClient) -> None:
        """Should convert Windows backslashes to forward slashes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            repo_client.upload_file(
                repo_id="test-repo-id",
                file_path="src\\subdir\\main.py",  # Windows path
                content=b"print('hello')",
            )

            call_args = mock_request.call_args
            url = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("url")
            # Should encode as forward slashes
            assert "src%2Fsubdir%2Fmain.py" in url
            assert "\\" not in url

    def test_upload_file_handles_special_characters(self, repo_client: RelaceRepoClient) -> None:
        """Should encode special characters in path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(
            repo_client, "_request_with_retry", return_value=mock_response
        ) as mock_request:
            repo_client.upload_file(
                repo_id="test-repo-id",
                file_path="src/file with spaces.py",
                content=b"print('hello')",
            )

            call_args = mock_request.call_args
            url = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("url")
            # Spaces should be encoded
            assert "%20" in url or "+" in url

    def test_upload_file_handles_204_response(self, repo_client: RelaceRepoClient) -> None:
        """Should handle 204 No Content response."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.is_success = True

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            result = repo_client.upload_file(
                repo_id="test-repo-id",
                file_path="src/main.py",
                content=b"print('hello')",
            )

        assert result["status"] == "ok"
        assert result["path"] == "src/main.py"

    def test_upload_file_handles_201_response_with_json(
        self, repo_client: RelaceRepoClient
    ) -> None:
        """Should handle 201 Created response with JSON body."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.is_success = True
        mock_response.json.return_value = {
            "repo_id": "test-repo-id",
            "repo_head": "abc123def456789",
            "changed_files": ["src/main.py"],
        }

        with patch.object(repo_client, "_request_with_retry", return_value=mock_response):
            result = repo_client.upload_file(
                repo_id="test-repo-id",
                file_path="src/main.py",
                content=b"print('hello')",
            )

        assert result["repo_id"] == "test-repo-id"
        assert result["repo_head"] == "abc123def456789"
        assert result["changed_files"] == ["src/main.py"]


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
