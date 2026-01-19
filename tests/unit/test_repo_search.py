"""Tests for cloud_search logic."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.repo.search import cloud_search_logic
from relace_mcp.tools.repo.state import SyncState


@pytest.fixture
def _mock_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(
        api_key="rlc-test-api-key",
        base_dir=str(tmp_path),
    )


@pytest.fixture
def mock_repo_client(_mock_config: RelaceConfig) -> MagicMock:
    client = MagicMock(spec=RelaceRepoClient)
    client.ensure_repo.return_value = "test-repo-id"
    client.retrieve.return_value = {
        "results": [
            {
                "filename": "src/auth.py",
                "content": "def authenticate(user): ...",
                "score": 0.85,
            },
            {
                "filename": "src/login.py",
                "content": "def login(username, password): ...",
                "score": 0.72,
            },
        ]
    }
    return client


@pytest.fixture
def mock_sync_state(monkeypatch: pytest.MonkeyPatch) -> SyncState:
    state = SyncState(
        repo_id="test-repo-id",
        repo_head="test-repo-head",
        last_sync="",
        repo_name="project",
        git_branch="main",
        git_head_sha="deadbeef",
        files={},
        skipped_files=set(),
    )
    monkeypatch.setattr(
        "relace_mcp.tools.repo.search.get_repo_identity",
        lambda _base_dir: ("project", "project__fp", "fp"),
    )
    monkeypatch.setattr("relace_mcp.tools.repo.search.load_sync_state", lambda _base_dir: state)
    return state


@pytest.mark.usefixtures("mock_sync_state")
class TestCloudSearchLogic:
    """Test cloud_search_logic function."""

    def test_search_returns_results(
        self, mock_repo_client: MagicMock, mock_sync_state: SyncState
    ) -> None:
        """Should return search results."""
        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="user authentication",
        )

        assert result["query"] == "user authentication"
        assert len(result["results"]) == 2
        assert result["repo_id"] == "test-repo-id"
        assert result["hash"] == mock_sync_state.git_head_sha
        assert result["result_count"] == 2

    def test_search_passes_parameters(
        self, mock_repo_client: MagicMock, mock_sync_state: SyncState
    ) -> None:
        """Should pass score_threshold and token_limit to retrieve."""
        cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="error handling",
            score_threshold=0.5,
            token_limit=10000,
        )

        mock_repo_client.retrieve.assert_called_once()
        call_kwargs = mock_repo_client.retrieve.call_args.kwargs
        assert call_kwargs["repo_id"] == "test-repo-id"
        assert call_kwargs["query"] == "error handling"
        assert call_kwargs["branch"] == ""
        assert call_kwargs["hash"] == mock_sync_state.git_head_sha
        assert call_kwargs["score_threshold"] == 0.5
        assert call_kwargs["token_limit"] == 10000
        assert call_kwargs["include_content"] is True

    def test_search_uses_default_parameters(self, mock_repo_client: MagicMock) -> None:
        """Should use default parameters when not specified."""
        cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="database connection",
        )

        call_kwargs = mock_repo_client.retrieve.call_args.kwargs
        assert call_kwargs["score_threshold"] == 0.3
        assert call_kwargs["token_limit"] == 30000

    def test_search_handles_empty_results(self, mock_repo_client: MagicMock) -> None:
        """Should handle empty search results."""
        mock_repo_client.retrieve.return_value = {"results": []}

        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="nonexistent code pattern",
        )

        assert result["results"] == []
        assert result["result_count"] == 0

    def test_search_returns_error_when_not_synced(self, mock_repo_client: MagicMock) -> None:
        """Should return an error when no sync state exists."""
        from relace_mcp.tools.repo import search as repo_search

        original = repo_search.load_sync_state
        try:
            repo_search.load_sync_state = lambda _base_dir: None
            result = cloud_search_logic(
                mock_repo_client,
                base_dir="/tmp/project",
                query="some query",
            )
        finally:
            repo_search.load_sync_state = original

        assert result["results"] == []
        assert result["repo_id"] is None
        assert "Run cloud_sync first" in result["error"]
        mock_repo_client.retrieve.assert_not_called()

    def test_search_handles_api_error(self, mock_repo_client: MagicMock) -> None:
        """Should handle API errors gracefully."""
        mock_repo_client.retrieve.side_effect = RuntimeError("API connection failed")

        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="some query",
        )

        assert "error" in result
        assert "API connection failed" in result["error"]
        assert result["results"] == []
        assert result["repo_id"] is None
        assert result["hash"] == ""

    def test_search_truncates_long_query_in_logs(self, mock_repo_client: MagicMock) -> None:
        """Should handle very long queries without issues."""
        long_query = "a" * 500  # Very long query

        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query=long_query,
        )

        # Should still work and pass the full query
        assert result["query"] == long_query
        call_kwargs = mock_repo_client.retrieve.call_args.kwargs
        assert call_kwargs["query"] == long_query


@pytest.mark.usefixtures("mock_sync_state")
class TestCloudSearchEdgeCases:
    """Test edge cases for cloud_search."""

    def test_search_with_unicode_query(self, mock_repo_client: MagicMock) -> None:
        """Should handle Unicode characters in query."""
        unicode_query = "處理用戶認證"

        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query=unicode_query,
        )

        assert result["query"] == unicode_query

    def test_search_with_special_characters(self, mock_repo_client: MagicMock) -> None:
        """Should handle special characters in query."""
        special_query = "function() { return 'test'; }"

        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query=special_query,
        )

        assert result["query"] == special_query

    def test_search_with_empty_query(self, mock_repo_client: MagicMock) -> None:
        """Should handle empty query."""
        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="",
        )

        assert result["query"] == ""
        # API should still be called
        mock_repo_client.retrieve.assert_called_once()


@pytest.mark.usefixtures("mock_sync_state")
class TestCloudSearchBranchParam:
    """Test branch parameter for cloud_search."""

    def test_branch_param_passed_to_retrieve(self, mock_repo_client: MagicMock) -> None:
        """Should pass branch parameter to retrieve API."""
        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="authentication flow",
            branch="feature-auth",
        )

        call_kwargs = mock_repo_client.retrieve.call_args.kwargs
        assert call_kwargs["branch"] == "feature-auth"
        assert result["branch"] == "feature-auth"

    def test_empty_branch_uses_default(self, mock_repo_client: MagicMock) -> None:
        """Should pass empty string to use API default branch."""
        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="some query",
            branch="",
        )

        call_kwargs = mock_repo_client.retrieve.call_args.kwargs
        assert call_kwargs["branch"] == ""
        assert result["branch"] == ""

    def test_branch_default_is_empty(self, mock_repo_client: MagicMock) -> None:
        """Should default to empty branch when not specified."""
        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="some query",
        )

        call_kwargs = mock_repo_client.retrieve.call_args.kwargs
        assert call_kwargs["branch"] == ""
        assert result["branch"] == ""

    def test_branch_in_error_response(self, mock_repo_client: MagicMock) -> None:
        """Should include branch in error response."""
        mock_repo_client.retrieve.side_effect = RuntimeError("API error")

        result = cloud_search_logic(
            mock_repo_client,
            base_dir="/tmp/project",
            query="some query",
            branch="main",
        )

        assert "error" in result
        assert result["branch"] == "main"
