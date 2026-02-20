from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.repo.cloud.clear import cloud_clear_logic
from relace_mcp.repo.cloud.info import cloud_info_logic
from relace_mcp.repo.cloud.search import cloud_search_logic
from relace_mcp.repo.cloud.sync import cloud_sync_logic
from relace_mcp.repo.core.state import (
    SyncState,
    clear_sync_state,
    load_sync_state,
    save_sync_state,
)


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=RelaceRepoClient)
    client.ensure_repo.return_value = "test-repo-id"
    client.update_repo.return_value = {"repo_head": "abc123def456"}
    client.retrieve.return_value = {
        "results": [{"filename": "main.py", "content": "print('hi')", "score": 0.9}]
    }
    client.delete_repo.return_value = True
    client.list_repos.return_value = [
        {
            "repo_id": "test-repo-id",
            "metadata": {"name": "myrepo__abcdef123456"},
            "auto_index": True,
            "created_at": "2025-01-01",
            "updated_at": "2025-01-02",
        }
    ]
    return client


SYNC_MODULE = "relace_mcp.repo.cloud.sync"
SEARCH_MODULE = "relace_mcp.repo.cloud.search"
CLEAR_MODULE = "relace_mcp.repo.cloud.clear"
INFO_MODULE = "relace_mcp.repo.cloud.info"


def _base_sync_patches(
    tmp_path: Path,
    *,
    cached_state: SyncState | None = None,
    repo_identity: tuple[str, str, str] = ("myrepo", "myrepo__abcdef123456", "abcdef123456"),
    git_info: tuple[str, str] = ("main", "a" * 40),
    tracked_files: list[str] | None = None,
    file_hashes: dict[str, str] | None = None,
    diff_ops: tuple[list[dict], dict[str, str], set[str]] | None = None,
):
    if tracked_files is None:
        tracked_files = ["main.py", "utils.py"]
    if file_hashes is None:
        file_hashes = {"main.py": "sha256:aaa", "utils.py": "sha256:bbb"}
    if diff_ops is None:
        diff_ops = (
            [
                {"type": "write", "filename": "main.py", "content": "print('hi')"},
                {"type": "write", "filename": "utils.py", "content": "x = 1"},
            ],
            {"main.py": "sha256:aaa", "utils.py": "sha256:bbb"},
            set(),
        )

    return [
        patch(f"{SYNC_MODULE}.get_git_root", return_value=tmp_path),
        patch(f"{SYNC_MODULE}.get_current_git_info", return_value=git_info),
        patch(f"{SYNC_MODULE}.get_repo_identity", return_value=repo_identity),
        patch(f"{SYNC_MODULE}._get_git_tracked_files", return_value=tracked_files),
        patch(f"{SYNC_MODULE}._compute_file_hashes", return_value=file_hashes),
        patch(f"{SYNC_MODULE}._compute_diff_operations", return_value=diff_ops),
        patch(f"{SYNC_MODULE}.save_sync_state", return_value=True),
        patch(f"{SYNC_MODULE}.load_sync_state", return_value=cached_state),
        patch(f"{SYNC_MODULE}.log_cloud_event"),
    ]


class TestCloudSyncIntegration:
    def test_full_sync_with_writes(self, tmp_path: Path, mock_client: MagicMock) -> None:
        patches = _base_sync_patches(tmp_path)
        for p in patches:
            p.start()
        try:
            result = cloud_sync_logic(mock_client, str(tmp_path))
        finally:
            for p in patches:
                p.stop()

        assert result["repo_id"] == "test-repo-id"
        assert result["repo_name"] == "myrepo"
        assert result["cloud_repo_name"] == "myrepo__abcdef123456"
        assert result["repo_head"] == "abc123def456"
        assert result["sync_mode"] == "safe_full"
        assert result["files_created"] == 2
        assert result["files_updated"] == 0
        assert result["total_files"] == 2
        assert "error" not in result
        mock_client.ensure_repo.assert_called_once()
        mock_client.update_repo.assert_called_once_with("test-repo-id", ANY, trace_id=ANY)

    def test_incremental_sync_cached_state(self, tmp_path: Path, mock_client: MagicMock) -> None:
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="old_head",
            last_sync="",
            repo_name="myrepo",
            cloud_repo_name="myrepo__abcdef123456",
            project_fingerprint="abcdef123456",
            git_branch="main",
            git_head_sha="a" * 40,
            files={"main.py": "sha256:aaa"},
        )
        diff_ops = (
            [{"type": "write", "filename": "utils.py", "content": "x = 1"}],
            {"main.py": "sha256:aaa", "utils.py": "sha256:bbb"},
            set(),
        )
        patches = _base_sync_patches(
            tmp_path,
            cached_state=cached,
            diff_ops=diff_ops,
        )
        for p in patches:
            p.start()
        try:
            result = cloud_sync_logic(mock_client, str(tmp_path))
        finally:
            for p in patches:
                p.stop()

        assert result["is_incremental"] is True
        assert result["sync_mode"] == "incremental"
        assert result["files_created"] == 1
        assert result["files_updated"] == 0
        assert "error" not in result

    def test_invalid_base_dir(self, tmp_path: Path, mock_client: MagicMock) -> None:
        with (
            patch(f"{SYNC_MODULE}.get_git_root", return_value=tmp_path),
            patch(f"{SYNC_MODULE}.get_current_git_info", return_value=("", "")),
            patch(f"{SYNC_MODULE}.get_repo_identity", return_value=("", "", "")),
            patch(f"{SYNC_MODULE}.log_cloud_event"),
        ):
            result = cloud_sync_logic(mock_client, str(tmp_path))

        assert result["error"] == "Invalid base_dir: cannot derive repository name."
        assert result["repo_id"] is None
        assert result["sync_mode"] == "error"
        mock_client.ensure_repo.assert_not_called()

    def test_client_exception_handling(self, tmp_path: Path, mock_client: MagicMock) -> None:
        mock_client.ensure_repo.side_effect = RuntimeError("API down")
        patches = _base_sync_patches(tmp_path)
        for p in patches:
            p.start()
        try:
            result = cloud_sync_logic(mock_client, str(tmp_path))
        finally:
            for p in patches:
                p.stop()

        assert "error" in result
        assert "API down" in result["error"]
        assert result["sync_mode"] == "error"
        assert result["repo_id"] is None


class TestCloudSearchIntegration:
    def _search_patches(
        self,
        *,
        repo_identity: tuple[str, str, str] = ("myrepo", "myrepo__abcdef123456", "abcdef123456"),
        cached_state: SyncState | None = None,
        git_info: tuple[str, str] = ("main", "a" * 40),
        git_dirty: bool = False,
    ):
        return [
            patch(f"{SEARCH_MODULE}.get_repo_identity", return_value=repo_identity),
            patch(f"{SEARCH_MODULE}.load_sync_state", return_value=cached_state),
            patch(f"{SEARCH_MODULE}.get_current_git_info", return_value=git_info),
            patch(f"{SEARCH_MODULE}.is_git_dirty", return_value=git_dirty),
            patch(f"{SEARCH_MODULE}.log_cloud_event"),
        ]

    def test_successful_search_with_cached_state(self, mock_client: MagicMock) -> None:
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="cloud_head_abc",
            last_sync="",
            git_branch="main",
            git_head_sha="a" * 40,
            files={"main.py": "sha256:aaa"},
        )
        patches = self._search_patches(cached_state=cached)
        for p in patches:
            p.start()
        try:
            result = cloud_search_logic(mock_client, "/fake", query="find main")
        finally:
            for p in patches:
                p.stop()

        assert result["repo_id"] == "test-repo-id"
        assert len(result["results"]) == 1
        assert result["query"] == "find main"
        assert "error" not in result
        mock_client.retrieve.assert_called_once()

    def test_no_sync_state_returns_error(self, mock_client: MagicMock) -> None:
        patches = self._search_patches(cached_state=None)
        for p in patches:
            p.start()
        try:
            result = cloud_search_logic(mock_client, "/fake", query="find main")
        finally:
            for p in patches:
                p.stop()

        assert "error" in result
        assert "No sync state found" in result["error"]
        assert result["repo_id"] is None
        mock_client.retrieve.assert_not_called()

    def test_invalid_base_dir(self, mock_client: MagicMock) -> None:
        with (
            patch(f"{SEARCH_MODULE}.get_repo_identity", return_value=("", "", "")),
            patch(f"{SEARCH_MODULE}.log_cloud_event"),
        ):
            result = cloud_search_logic(mock_client, "/fake", query="test")

        assert result["error"] == "Invalid base_dir: cannot derive repository name."
        assert result["repo_id"] is None

    def test_client_exception_handling(self, mock_client: MagicMock) -> None:
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="head",
            last_sync="",
            git_branch="main",
            git_head_sha="a" * 40,
            files={},
        )
        mock_client.retrieve.side_effect = RuntimeError("Network error")
        patches = self._search_patches(cached_state=cached)
        for p in patches:
            p.start()
        try:
            result = cloud_search_logic(mock_client, "/fake", query="test")
        finally:
            for p in patches:
                p.stop()

        assert "error" in result
        assert "Network error" in result["error"]


class TestCloudClearIntegration:
    def test_confirm_false_returns_cancelled(self, mock_client: MagicMock) -> None:
        result = cloud_clear_logic(mock_client, "/fake", confirm=False)

        assert result["status"] == "cancelled"
        assert result["repo_id"] is None
        mock_client.delete_repo.assert_not_called()

    def test_direct_repo_id_mode_success(self, mock_client: MagicMock) -> None:
        with patch(f"{CLEAR_MODULE}.log_cloud_event"):
            result = cloud_clear_logic(mock_client, "/fake", confirm=True, repo_id="direct-id")

        assert result["status"] == "deleted"
        assert result["repo_id"] == "direct-id"
        mock_client.delete_repo.assert_called_once_with("direct-id", trace_id=ANY)

    def test_direct_repo_id_mode_failure(self, mock_client: MagicMock) -> None:
        mock_client.delete_repo.return_value = False
        with patch(f"{CLEAR_MODULE}.log_cloud_event"):
            result = cloud_clear_logic(mock_client, "/fake", confirm=True, repo_id="direct-id")

        assert result["status"] == "error"
        assert result["repo_id"] == "direct-id"

    def test_base_dir_mode_with_sync_state(self, mock_client: MagicMock) -> None:
        cached = SyncState(repo_id="state-repo-id", repo_head="abc", last_sync="", files={})
        with (
            patch(f"{CLEAR_MODULE}.get_repo_identity", return_value=("myrepo", "myrepo__fp", "fp")),
            patch(f"{CLEAR_MODULE}.load_sync_state", return_value=cached),
            patch(f"{CLEAR_MODULE}.clear_sync_state") as mock_clear,
            patch(f"{CLEAR_MODULE}.log_cloud_event"),
        ):
            result = cloud_clear_logic(mock_client, "/fake", confirm=True)

        assert result["status"] == "deleted"
        assert result["repo_id"] == "state-repo-id"
        mock_client.delete_repo.assert_called_once_with("state-repo-id", trace_id=ANY)
        mock_clear.assert_called_once_with("/fake")

    def test_base_dir_mode_no_repo_found(self, mock_client: MagicMock) -> None:
        mock_client.list_repos.return_value = []
        with (
            patch(f"{CLEAR_MODULE}.get_repo_identity", return_value=("myrepo", "myrepo__fp", "fp")),
            patch(f"{CLEAR_MODULE}.load_sync_state", return_value=None),
            patch(f"{CLEAR_MODULE}.clear_sync_state") as mock_clear,
            patch(f"{CLEAR_MODULE}.log_cloud_event"),
        ):
            result = cloud_clear_logic(mock_client, "/fake", confirm=True)

        assert result["status"] == "not_found"
        mock_client.delete_repo.assert_not_called()
        mock_clear.assert_called_once_with("/fake")


class TestCloudInfoIntegration:
    def _info_patches(
        self,
        *,
        repo_identity: tuple[str, str, str] = ("myrepo", "myrepo__abcdef123456", "abcdef123456"),
        git_info: tuple[str, str] = ("main", "a" * 40),
        git_dirty: bool = False,
        cached_state: SyncState | None = None,
    ):
        return [
            patch(f"{INFO_MODULE}.get_repo_identity", return_value=repo_identity),
            patch(f"{INFO_MODULE}.get_current_git_info", return_value=git_info),
            patch(f"{INFO_MODULE}.is_git_dirty", return_value=git_dirty),
            patch(f"{INFO_MODULE}.load_sync_state", return_value=cached_state),
            patch(f"{INFO_MODULE}.log_cloud_event"),
        ]

    def test_with_sync_state_and_cloud_repo(self, mock_client: MagicMock) -> None:
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="cloud_head",
            last_sync="2025-01-01T00:00:00",
            repo_name="myrepo",
            cloud_repo_name="myrepo__abcdef123456",
            project_fingerprint="abcdef123456",
            git_branch="main",
            git_head_sha="a" * 40,
            files={"main.py": "sha256:aaa"},
        )
        patches = self._info_patches(cached_state=cached)
        for p in patches:
            p.start()
        try:
            result = cloud_info_logic(mock_client, "/fake")
        finally:
            for p in patches:
                p.stop()

        assert result["repo_name"] == "myrepo"
        assert result["local"]["git_branch"] == "main"
        assert result["synced"] is not None
        assert result["synced"]["repo_id"] == "test-repo-id"
        assert result["synced"]["tracked_files"] == 1
        assert result["cloud"] is not None
        assert result["cloud"]["repo_id"] == "test-repo-id"
        assert result["status"]["needs_sync"] is False
        assert "error" not in result

    def test_no_sync_state_needs_sync(self, mock_client: MagicMock) -> None:
        patches = self._info_patches(cached_state=None)
        for p in patches:
            p.start()
        try:
            result = cloud_info_logic(mock_client, "/fake")
        finally:
            for p in patches:
                p.stop()

        assert result["synced"] is None
        assert result["status"]["needs_sync"] is True
        assert result["status"]["recommended_action"] is not None
        assert "error" not in result

    def test_invalid_base_dir(self, mock_client: MagicMock) -> None:
        with (
            patch(f"{INFO_MODULE}.get_repo_identity", return_value=("", "", "")),
            patch(f"{INFO_MODULE}.log_cloud_event"),
        ):
            result = cloud_info_logic(mock_client, "/fake")

        assert result["error"] == "Invalid base_dir: cannot derive repository name."
        assert result["local"] is None


class TestCloudStateInteraction:
    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        state = SyncState(
            repo_id="rt-repo-id",
            repo_head="rt-head-123",
            last_sync="",
            repo_name="myrepo",
            cloud_repo_name="myrepo__abcdef123456",
            project_fingerprint="abcdef123456",
            git_branch="main",
            git_head_sha="b" * 40,
            files={"a.py": "sha256:aaa", "b.py": "sha256:bbb"},
            skipped_files={"c.bin"},
        )
        fake_root = tmp_path / "myrepo"
        fake_root.mkdir()

        with (
            patch(
                "relace_mcp.repo.core.state.get_git_root",
                return_value=fake_root,
            ),
            patch(
                "relace_mcp.repo.core.state.get_git_remote_origin_url",
                return_value="https://github.com/user/myrepo.git",
            ),
        ):
            saved = save_sync_state(str(fake_root), state)
            assert saved is True

            loaded = load_sync_state(str(fake_root))

        assert loaded is not None
        assert loaded.repo_id == "rt-repo-id"
        assert loaded.repo_head == "rt-head-123"
        assert loaded.git_branch == "main"
        assert loaded.git_head_sha == "b" * 40
        assert loaded.files == {"a.py": "sha256:aaa", "b.py": "sha256:bbb"}
        assert loaded.skipped_files == {"c.bin"}
        assert loaded.last_sync != ""

    def test_clear_sync_state_removes_file(self, tmp_path: Path) -> None:
        state = SyncState(
            repo_id="rm-repo-id",
            repo_head="rm-head",
            last_sync="",
            repo_name="myrepo",
            files={},
        )
        fake_root = tmp_path / "myrepo"
        fake_root.mkdir()

        with (
            patch(
                "relace_mcp.repo.core.state.get_git_root",
                return_value=fake_root,
            ),
            patch(
                "relace_mcp.repo.core.state.get_git_remote_origin_url",
                return_value="https://github.com/user/myrepo.git",
            ),
        ):
            save_sync_state(str(fake_root), state)
            loaded = load_sync_state(str(fake_root))
            assert loaded is not None

            cleared = clear_sync_state(str(fake_root))
            assert cleared is True

            loaded_after = load_sync_state(str(fake_root))
            assert loaded_after is None
