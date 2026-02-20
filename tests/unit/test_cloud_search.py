from unittest.mock import MagicMock, patch

from relace_mcp.clients.exceptions import RelaceAPIError
from relace_mcp.repo.cloud.search import cloud_search_logic


def _make_sync_state(**overrides):
    state = MagicMock()
    state.repo_id = overrides.get("repo_id", "repo-123")
    state.git_head_sha = overrides.get("git_head_sha", "aaa111")
    state.git_branch = overrides.get("git_branch", "main")
    state.repo_head = overrides.get("repo_head", "cloud-abc")
    state.cloud_repo_name = overrides.get("cloud_repo_name", "owner/repo")
    state.files_truncated = overrides.get("files_truncated", False)
    state.files_selected = overrides.get("files_selected", 100)
    state.files_found = overrides.get("files_found", 100)
    state.file_limit = overrides.get("file_limit", 50000)
    state.skipped_files = overrides.get("skipped_files", [])
    return state


class TestCloudSearch404Retry:
    @patch("relace_mcp.repo.cloud.search.log_cloud_event")
    @patch("relace_mcp.repo.cloud.search.load_sync_state")
    @patch("relace_mcp.repo.cloud.search.is_git_dirty", return_value=False)
    @patch("relace_mcp.repo.cloud.search.get_current_git_info", return_value=("main", "aaa111"))
    @patch(
        "relace_mcp.repo.cloud.search.get_repo_identity",
        return_value=("my-repo", "owner/repo", "fp"),
    )
    def test_repo_not_found_404_no_retry(self, _id, _git, _dirty, mock_sync, _log):
        mock_sync.return_value = _make_sync_state()
        client = MagicMock()

        api_err = RelaceAPIError(status_code=404, code="not_found", message="repository not found")
        call_err = RuntimeError("retrieve failed")
        call_err.__cause__ = api_err
        client.retrieve.side_effect = call_err

        result = cloud_search_logic(client, "/tmp/repo", "auth logic")

        assert "error" in result
        # Should NOT retry — only 1 call total
        assert client.retrieve.call_count == 1
        # Should NOT be marked as commit-not-indexed retryable
        assert result.get("retryable") is not True

    @patch("relace_mcp.repo.cloud.search.log_cloud_event")
    @patch("relace_mcp.repo.cloud.search.load_sync_state")
    @patch("relace_mcp.repo.cloud.search.is_git_dirty", return_value=False)
    @patch("relace_mcp.repo.cloud.search.get_current_git_info", return_value=("main", "aaa111"))
    @patch(
        "relace_mcp.repo.cloud.search.get_repo_identity",
        return_value=("my-repo", "owner/repo", "fp"),
    )
    def test_commit_not_indexed_404_retries(self, _id, _git, _dirty, mock_sync, _log):
        mock_sync.return_value = _make_sync_state()
        client = MagicMock()

        api_err = RelaceAPIError(
            status_code=404, code="commit_not_indexed", message="commit cloud-abc not indexed"
        )
        call_err = RuntimeError("retrieve failed")
        call_err.__cause__ = api_err
        # Fail 3 times, succeed on 4th
        client.retrieve.side_effect = [call_err, call_err, call_err, {"results": []}]

        with patch("relace_mcp.repo.cloud.search.time.sleep"):
            result = cloud_search_logic(client, "/tmp/repo", "auth logic")

        assert "error" not in result
        assert client.retrieve.call_count == 4

    @patch("relace_mcp.repo.cloud.search.log_cloud_event")
    @patch("relace_mcp.repo.cloud.search.load_sync_state")
    @patch("relace_mcp.repo.cloud.search.is_git_dirty", return_value=False)
    @patch("relace_mcp.repo.cloud.search.get_current_git_info", return_value=("main", "aaa111"))
    @patch(
        "relace_mcp.repo.cloud.search.get_repo_identity",
        return_value=("my-repo", "owner/repo", "fp"),
    )
    def test_generic_404_no_hash_no_retry(self, _id, _git, _dirty, mock_sync, _log):
        mock_sync.return_value = _make_sync_state(repo_head="")
        client = MagicMock()

        api_err = RelaceAPIError(
            status_code=404, code="commit_not_indexed", message="commit not indexed"
        )
        call_err = RuntimeError("retrieve failed")
        call_err.__cause__ = api_err
        client.retrieve.side_effect = call_err

        result = cloud_search_logic(client, "/tmp/repo", "query")

        assert "error" in result
        assert client.retrieve.call_count == 1

    @patch("relace_mcp.repo.cloud.search.log_cloud_event")
    @patch("relace_mcp.repo.cloud.search.load_sync_state")
    @patch("relace_mcp.repo.cloud.search.is_git_dirty", return_value=False)
    @patch("relace_mcp.repo.cloud.search.get_current_git_info", return_value=("main", "aaa111"))
    @patch(
        "relace_mcp.repo.cloud.search.get_repo_identity",
        return_value=("my-repo", "owner/repo", "fp"),
    )
    def test_commit_404_exhausted_retries_marks_retryable(self, _id, _git, _dirty, mock_sync, _log):
        mock_sync.return_value = _make_sync_state()
        client = MagicMock()

        api_err = RelaceAPIError(
            status_code=404, code="commit_not_indexed", message="commit cloud-abc not indexed"
        )
        call_err = RuntimeError("retrieve failed")
        call_err.__cause__ = api_err
        client.retrieve.side_effect = call_err

        with patch("relace_mcp.repo.cloud.search.time.sleep"):
            result = cloud_search_logic(client, "/tmp/repo", "query")

        assert "error" in result
        assert result.get("retryable") is True
        assert "recommended_action" in result
        # 1 initial + 3 retries = 4 total
        assert client.retrieve.call_count == 4
