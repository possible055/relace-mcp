from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.tools.repo.clear import cloud_clear_logic
from relace_mcp.tools.repo.state import SyncState


def _create_mock_repo_client(repo_name: str) -> MagicMock:
    """Create mock client with configurable repo name."""
    client = MagicMock(spec=RelaceRepoClient)
    client.list_repos.return_value = [{"metadata": {"name": repo_name}, "repo_id": "api-repo-id"}]
    client.delete_repo.return_value = True
    return client


def test_cloud_clear_requires_confirm(tmp_path: Path) -> None:
    """Should return cancelled status if confirm is False."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)
    result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=False)

    assert result["status"] == "cancelled"
    assert isinstance(result.get("trace_id"), str)
    assert len(result["trace_id"]) == 8
    mock_repo_client.delete_repo.assert_not_called()


def test_cloud_clear_uses_sync_state(tmp_path: Path) -> None:
    """Should use repo_id from sync state if available."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)
    cached = SyncState(repo_id="state-repo-id", repo_head="abc", last_sync="", files={})

    with patch(
        "relace_mcp.tools.repo.clear.get_repo_identity",
        return_value=(tmp_path.name, tmp_path.name, "fp"),
    ):
        with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=cached):
            with patch("relace_mcp.tools.repo.clear.clear_sync_state") as mock_clear_state:
                result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

                assert result["status"] == "deleted"
                assert result["repo_id"] == "state-repo-id"
                assert isinstance(result.get("trace_id"), str)
                assert len(result["trace_id"]) == 8
                mock_repo_client.delete_repo.assert_called_with("state-repo-id", trace_id=ANY)
                mock_clear_state.assert_called_with(str(tmp_path))


def test_cloud_clear_searches_api_fallback(tmp_path: Path) -> None:
    """Should fallback to API search if sync state missing."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)

    with patch(
        "relace_mcp.tools.repo.clear.get_repo_identity",
        return_value=(tmp_path.name, tmp_path.name, "fp"),
    ):
        with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=None):
            with patch("relace_mcp.tools.repo.clear.clear_sync_state"):
                result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

                assert result["status"] == "deleted"
                assert result["repo_id"] == "api-repo-id"
                mock_repo_client.list_repos.assert_called_once()
                mock_repo_client.delete_repo.assert_called_with("api-repo-id", trace_id=ANY)


def test_cloud_clear_not_found(tmp_path: Path) -> None:
    """Should handle repo not found scenario."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)
    mock_repo_client.list_repos.return_value = []

    with patch(
        "relace_mcp.tools.repo.clear.get_repo_identity",
        return_value=(tmp_path.name, tmp_path.name, "fp"),
    ):
        with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=None):
            with patch("relace_mcp.tools.repo.clear.clear_sync_state") as mock_clear_state:
                result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

                assert result["status"] == "not_found"
                mock_repo_client.delete_repo.assert_not_called()
                # Should still clear sync state just in case
                mock_clear_state.assert_called_with(str(tmp_path))


def test_cloud_clear_delete_failure(tmp_path: Path) -> None:
    """Should handle delete failure."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)
    cached = SyncState(repo_id="id", repo_head="", last_sync="")
    mock_repo_client.delete_repo.return_value = False

    with patch(
        "relace_mcp.tools.repo.clear.get_repo_identity",
        return_value=(tmp_path.name, tmp_path.name, "fp"),
    ):
        with patch("relace_mcp.tools.repo.clear.load_sync_state", return_value=cached):
            with patch("relace_mcp.tools.repo.clear.clear_sync_state") as mock_clear_state:
                result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=True)

                assert result["status"] == "error"
                # Should NOT clear sync state on failure
                mock_clear_state.assert_not_called()


def test_cloud_clear_direct_repo_id(tmp_path: Path) -> None:
    """Should delete directly by repo_id without base_dir lookup."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)

    result = cloud_clear_logic(
        mock_repo_client, str(tmp_path), confirm=True, repo_id="direct-repo-id"
    )

    assert result["status"] == "deleted"
    assert result["repo_id"] == "direct-repo-id"
    mock_repo_client.delete_repo.assert_called_with("direct-repo-id", trace_id=ANY)
    mock_repo_client.list_repos.assert_not_called()


def test_cloud_clear_direct_repo_id_failure(tmp_path: Path) -> None:
    """Should handle direct repo_id delete failure."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)
    mock_repo_client.delete_repo.return_value = False

    result = cloud_clear_logic(
        mock_repo_client, str(tmp_path), confirm=True, repo_id="fail-repo-id"
    )

    assert result["status"] == "error"
    assert result["repo_id"] == "fail-repo-id"


def test_cloud_clear_direct_repo_id_requires_confirm(tmp_path: Path) -> None:
    """Direct repo_id mode still requires confirm."""
    mock_repo_client = _create_mock_repo_client(tmp_path.name)

    result = cloud_clear_logic(mock_repo_client, str(tmp_path), confirm=False, repo_id="some-id")

    assert result["status"] == "cancelled"
    mock_repo_client.delete_repo.assert_not_called()
