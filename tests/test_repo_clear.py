from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.tools.repo.clear import cloud_clear_logic
from relace_mcp.tools.repo.state import SyncState


@pytest.fixture
def mock_repo_client() -> MagicMock:
    client = MagicMock(spec=RelaceRepoClient)
    client.get_repo_name_from_base_dir.return_value = "test-project"
    client.list_repos.return_value = [
        {"metadata": {"name": "test-project"}, "repo_id": "api-repo-id"}
    ]
    client.delete_repo.return_value = True
    return client


def test_cloud_clear_requires_confirm(mock_repo_client: MagicMock, tmp_path: Path) -> None:
    """Should return cancelled status if confirm is False."""
    result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=False)

    assert result["status"] == "cancelled"
    mock_repo_client.delete_repo.assert_not_called()


def test_cloud_clear_uses_sync_state(mock_repo_client: MagicMock, tmp_path: Path) -> None:
    """Should use repo_id from sync state if available."""
    cached = SyncState(repo_id="state-repo-id", repo_head="abc", last_sync="", files={})

    with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=cached):
        with patch("relace_mcp.tools.repo.clear.clear_sync_state") as mock_clear_state:
            result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

            assert result["status"] == "deleted"
            assert result["repo_id"] == "state-repo-id"
            mock_repo_client.delete_repo.assert_called_with("state-repo-id", trace_id=ANY)
            mock_clear_state.assert_called_with("test-project")


def test_cloud_clear_searches_api_fallback(mock_repo_client: MagicMock, tmp_path: Path) -> None:
    """Should fallback to API search if sync state missing."""
    with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=None):
        with patch("relace_mcp.tools.repo.clear.clear_sync_state"):
            result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

            assert result["status"] == "deleted"
            assert result["repo_id"] == "api-repo-id"
            mock_repo_client.list_repos.assert_called_once()
            mock_repo_client.delete_repo.assert_called_with("api-repo-id", trace_id=ANY)


def test_cloud_clear_not_found(mock_repo_client: MagicMock, tmp_path: Path) -> None:
    """Should handle repo not found scenario."""
    mock_repo_client.list_repos.return_value = []

    with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=None):
        with patch("relace_mcp.tools.repo.clear.clear_sync_state") as mock_clear_state:
            result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

            assert result["status"] == "not_found"
            mock_repo_client.delete_repo.assert_not_called()
            # Should still clear sync state just in case
            mock_clear_state.assert_called_with("test-project")


def test_cloud_clear_delete_failure(mock_repo_client: MagicMock, tmp_path: Path) -> None:
    """Should handle delete failure."""
    cached = SyncState(repo_id="id", repo_head="", last_sync="")
    mock_repo_client.delete_repo.return_value = False

    with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=cached):
        with patch("relace_mcp.tools.repo.clear.clear_sync_state") as mock_clear_state:
            result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

            assert result["status"] == "error"
            # Should NOT clear sync state on failure
            mock_clear_state.assert_not_called()
