"""Tests for cloud_list and cloud_info logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.repo.info import cloud_info_logic
from relace_mcp.tools.repo.list import cloud_list_logic
from relace_mcp.tools.repo.state import SyncState


@pytest.fixture
def mock_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(
        api_key="rlc-test-api-key",
        base_dir=str(tmp_path),
    )


@pytest.fixture
def mock_repo_client(mock_config: RelaceConfig) -> MagicMock:
    client = MagicMock(spec=RelaceRepoClient)
    client.get_repo_name_from_base_dir.return_value = "test-project"
    client.list_repos.return_value = [
        {
            "repo_id": "repo-1",
            "metadata": {"name": "project-one"},
            "auto_index": True,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z",
        },
        {
            "repo_id": "repo-2",
            "metadata": {"name": "project-two"},
            "auto_index": False,
            "created_at": "2025-01-10T00:00:00Z",
            "updated_at": "2025-01-20T00:00:00Z",
        },
    ]
    return client


class TestCloudListLogic:
    """Test cloud_list_logic function."""

    def test_list_returns_repos(self, mock_repo_client: MagicMock) -> None:
        """Should return list of repos."""
        result = cloud_list_logic(mock_repo_client)

        assert result["count"] == 2
        assert len(result["repos"]) == 2
        assert result["has_more"] is False

    def test_list_extracts_repo_fields(self, mock_repo_client: MagicMock) -> None:
        """Should extract correct fields from repos."""
        result = cloud_list_logic(mock_repo_client)

        repo1 = result["repos"][0]
        assert repo1["repo_id"] == "repo-1"
        assert repo1["name"] == "project-one"
        assert repo1["auto_index"] is True

    def test_list_handles_empty_result(self, mock_repo_client: MagicMock) -> None:
        """Should handle empty repo list."""
        mock_repo_client.list_repos.return_value = []

        result = cloud_list_logic(mock_repo_client)

        assert result["count"] == 0
        assert result["repos"] == []
        assert result["has_more"] is False

    def test_list_handles_api_error(self, mock_repo_client: MagicMock) -> None:
        """Should handle API errors gracefully."""
        mock_repo_client.list_repos.side_effect = RuntimeError("API connection failed")

        result = cloud_list_logic(mock_repo_client)

        assert "error" in result
        assert "API connection failed" in result["error"]
        assert result["count"] == 0

    def test_list_detects_pagination(self, mock_repo_client: MagicMock) -> None:
        """Should detect when there are more repos (pagination safety limit).

        list_repos now auto-paginates, so has_more only triggers at 10,000 repos
        (the safety limit of 100 pages * 100 per page).
        """
        # Return 10,000 repos → has_more should be True (safety limit reached)
        mock_repo_client.list_repos.return_value = [
            {"repo_id": f"repo-{i}", "metadata": {"name": f"project-{i}"}} for i in range(10000)
        ]

        result = cloud_list_logic(mock_repo_client)

        assert result["count"] == 10000
        assert result["has_more"] is True

    def test_list_no_pagination_for_small_list(self, mock_repo_client: MagicMock) -> None:
        """Should not show has_more for lists under 10,000."""
        mock_repo_client.list_repos.return_value = [
            {"repo_id": f"repo-{i}", "metadata": {"name": f"project-{i}"}} for i in range(100)
        ]

        result = cloud_list_logic(mock_repo_client)

        assert result["count"] == 100
        assert result["has_more"] is False


class TestCloudInfoLogic:
    """Test cloud_info_logic function."""

    def test_info_returns_local_git_info(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should return local git info."""
        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=None):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        assert result["local"]["git_branch"] == "main"
        assert result["local"]["git_head"] == "abc123de"

    def test_info_returns_synced_state(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should return synced state info."""
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="head123456789",
            last_sync="2025-01-15T00:00:00Z",
            git_branch="develop",
            git_head_sha="old_head_sha_123456789012345678901234",
            files={"main.py": "sha256:abc", "utils.py": "sha256:def"},
            skipped_files={"binary.dat"},
        )

        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=cached):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        synced = result["synced"]
        assert synced["repo_id"] == "test-repo-id"
        assert synced["git_branch"] == "develop"
        assert synced["tracked_files"] == 2
        assert synced["skipped_files"] == 1

    def test_info_detects_ref_change(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should detect when git ref changed since last sync."""
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="head123",
            last_sync="2025-01-15T00:00:00Z",
            git_branch="main",
            git_head_sha="old_head_sha_123456789012345678901234",
            files={},
        )

        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            # Current head is different from cached
            mock_git.return_value = ("main", "new_head_sha_987654321098765432109876")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=cached):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        assert result["status"]["ref_changed"] is True
        assert result["status"]["needs_sync"] is True
        assert result["status"]["recommended_action"] is not None

    def test_info_no_sync_needed_when_head_unchanged(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Should not suggest sync when git HEAD unchanged."""
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="head123",
            last_sync="2025-01-15T00:00:00Z",
            git_branch="main",
            git_head_sha="same_head_sha_123456789012345678901234",
            files={},
        )

        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            # Same head as cached
            mock_git.return_value = ("main", "same_head_sha_123456789012345678901234")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=cached):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        assert result["status"]["ref_changed"] is False
        assert result["status"]["needs_sync"] is False

    def test_info_finds_cloud_repo(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should find matching cloud repo in list."""
        mock_repo_client.list_repos.return_value = [
            {
                "repo_id": "cloud-repo-id",
                "metadata": {"name": "test-project"},
                "auto_index": True,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-15T00:00:00Z",
            },
        ]

        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=None):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        assert result["cloud"] is not None
        assert result["cloud"]["repo_id"] == "cloud-repo-id"

    def test_info_handles_no_cloud_repo(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should handle when no matching cloud repo exists."""
        mock_repo_client.list_repos.return_value = [
            {
                "repo_id": "other-repo-id",
                "metadata": {"name": "other-project"},
            },
        ]

        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=None):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        assert result["cloud"] is None

    def test_info_handles_list_api_error(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should handle list API errors gracefully."""
        mock_repo_client.list_repos.side_effect = RuntimeError("API error")

        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=None):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        # Should still return local info
        assert result["local"]["git_branch"] == "main"
        # Cloud should be None due to error
        assert result["cloud"] is None
        # No error in result (we handle list failure gracefully)
        assert "error" not in result

    def test_info_suggests_sync_when_no_state(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Should suggest sync when no sync state exists."""
        with patch("relace_mcp.tools.repo.info.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.info.load_sync_state", return_value=None):
                result = cloud_info_logic(mock_repo_client, str(tmp_path))

        assert result["synced"] is None
        assert result["status"]["needs_sync"] is True
        assert "Run cloud_sync()" in result["status"]["recommended_action"]
