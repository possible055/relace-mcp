"""Tests for cloud_sync logic with incremental support."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.apply.file_io import set_project_encoding
from relace_mcp.tools.repo.state import (
    SyncState,
    compute_file_hash,
    get_current_git_info,
    load_sync_state,
    save_sync_state,
)
from relace_mcp.tools.repo.sync import (
    CODE_EXTENSIONS,
    SPECIAL_FILENAMES,
    _compute_diff_operations,
    _compute_file_hashes,
    _get_git_tracked_files,
    _read_file_content,
    _scan_directory,
    cloud_sync_logic,
)


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
    client.ensure_repo.return_value = "test-repo-id"
    client.update_repo.return_value = {"repo_head": "abc123def456", "changed_files": []}
    return client


class TestGetGitTrackedFiles:
    """Test _get_git_tracked_files function."""

    def test_returns_none_when_not_git_repo(self, tmp_path: Path) -> None:
        """Should return None when not in a git repository."""
        result = _get_git_tracked_files(str(tmp_path))
        # May return None or empty list depending on git behavior
        assert result is None or result == []

    def test_returns_files_in_git_repo(self, tmp_path: Path) -> None:
        """Should return tracked files in git repository."""
        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and track a file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)

        result = _get_git_tracked_files(str(tmp_path))

        assert result is not None
        assert "test.py" in result


class TestScanDirectory:
    """Test _scan_directory function."""

    def test_finds_python_files(self, tmp_path: Path) -> None:
        """Should find Python files."""
        py_file = tmp_path / "main.py"
        py_file.write_text("print('hello')")

        files = _scan_directory(str(tmp_path))

        assert "main.py" in files

    def test_finds_nested_files(self, tmp_path: Path) -> None:
        """Should find files in subdirectories."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "app.py"
        py_file.write_text("print('hello')")

        files = _scan_directory(str(tmp_path))

        # Path should use forward slashes
        assert any("app.py" in f for f in files)

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        """Should exclude __pycache__ directory."""
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        pyc_file = pycache / "module.cpython-312.pyc"
        pyc_file.write_bytes(b"compiled")

        files = _scan_directory(str(tmp_path))

        assert not any("__pycache__" in f for f in files)

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        """Should exclude node_modules directory."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        js_file = node_modules / "lodash" / "index.js"
        js_file.parent.mkdir()
        js_file.write_text("module.exports = {}")

        files = _scan_directory(str(tmp_path))

        assert not any("node_modules" in f for f in files)

    def test_excludes_hidden_files(self, tmp_path: Path) -> None:
        """Should exclude hidden files."""
        hidden_file = tmp_path / ".secret"
        hidden_file.write_text("secret")

        files = _scan_directory(str(tmp_path))

        assert not any(".secret" in f for f in files)

    def test_includes_special_filenames(self, tmp_path: Path) -> None:
        """Should include special filenames like Dockerfile."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.12")

        makefile = tmp_path / "Makefile"
        makefile.write_text("all: build")

        files = _scan_directory(str(tmp_path))

        # Case-insensitive matching
        assert any("Dockerfile" in f or "dockerfile" in f.lower() for f in files)
        assert any("Makefile" in f or "makefile" in f.lower() for f in files)

    def test_excludes_large_files(self, tmp_path: Path) -> None:
        """Should exclude files larger than MAX_FILE_SIZE_BYTES."""
        large_file = tmp_path / "large.py"
        # Write 2MB of data (exceeds 1MB limit)
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))

        files = _scan_directory(str(tmp_path))

        assert "large.py" not in files

    def test_excludes_non_code_extensions(self, tmp_path: Path) -> None:
        """Should exclude non-code file extensions."""
        image = tmp_path / "logo.png"
        image.write_bytes(b"\x89PNG")

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF")

        files = _scan_directory(str(tmp_path))

        assert "logo.png" not in files
        assert "doc.pdf" not in files


class TestReadFileContent:
    """Test _read_file_content function."""

    def test_reads_file_content(self, tmp_path: Path) -> None:
        """Should read file content as bytes."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')", encoding="utf-8")

        content = _read_file_content(str(tmp_path), "test.py")

        assert content == b"print('hello')"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Should return None for non-existent file."""
        content = _read_file_content(str(tmp_path), "nonexistent.py")

        assert content is None

    def test_returns_none_for_large_file(self, tmp_path: Path) -> None:
        """Should return None for files exceeding size limit."""
        large_file = tmp_path / "large.py"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))

        content = _read_file_content(str(tmp_path), "large.py")

        assert content is None


class TestComputeFileHashes:
    """Test _compute_file_hashes function."""

    def test_computes_hashes_for_files(self, tmp_path: Path) -> None:
        """Should compute SHA-256 hashes for files."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        hashes = _compute_file_hashes(str(tmp_path), ["main.py", "utils.py"])

        assert len(hashes) == 2
        assert "main.py" in hashes
        assert "utils.py" in hashes
        assert hashes["main.py"].startswith("sha256:")
        assert hashes["utils.py"].startswith("sha256:")

    def test_skips_missing_files(self, tmp_path: Path) -> None:
        """Should skip files that don't exist."""
        (tmp_path / "exists.py").write_text("print('hello')")

        hashes = _compute_file_hashes(str(tmp_path), ["exists.py", "missing.py"])

        assert len(hashes) == 1
        assert "exists.py" in hashes


class TestComputeDiffOperations:
    """Test _compute_diff_operations function."""

    def test_all_files_new_without_cache(self, tmp_path: Path) -> None:
        """All files should be write operations without cached state."""
        (tmp_path / "main.py").write_text("print('hello')")
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        operations, new_hashes, new_skipped = _compute_diff_operations(str(tmp_path), hashes, None)

        assert len(operations) == 1
        assert operations[0]["type"] == "write"
        assert operations[0]["filename"] == "main.py"
        assert operations[0]["content"] == "print('hello')"
        assert len(new_skipped) == 0

    def test_unchanged_files_skipped(self, tmp_path: Path) -> None:
        """Unchanged files should not generate operations."""
        (tmp_path / "main.py").write_text("print('hello')")
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        # Create cached state with same hash
        cached = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="",
            files=hashes.copy(),
        )

        operations, new_hashes, new_skipped = _compute_diff_operations(
            str(tmp_path), hashes, cached
        )

        assert len(operations) == 0
        assert len(new_hashes) == 1
        assert len(new_skipped) == 0

    def test_modified_files_detected(self, tmp_path: Path) -> None:
        """Modified files should generate write operations."""
        (tmp_path / "main.py").write_text("print('modified')")
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        # Create cached state with different hash
        cached = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="",
            files={"main.py": "sha256:different_hash"},
        )

        operations, new_hashes, new_skipped = _compute_diff_operations(
            str(tmp_path), hashes, cached
        )

        assert len(operations) == 1
        assert operations[0]["type"] == "write"
        assert operations[0]["filename"] == "main.py"
        assert len(new_skipped) == 0

    def test_deleted_files_detected(self, tmp_path: Path) -> None:
        """Deleted files should generate delete operations."""
        # No files exist now
        hashes: dict[str, str] = {}

        # But cached state had a file
        cached = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="",
            files={"deleted.py": "sha256:some_hash"},
        )

        operations, new_hashes, new_skipped = _compute_diff_operations(
            str(tmp_path), hashes, cached
        )

        assert len(operations) == 1
        assert operations[0]["type"] == "delete"
        assert operations[0]["filename"] == "deleted.py"
        assert len(new_skipped) == 0

    def test_mixed_operations(self, tmp_path: Path) -> None:
        """Should handle mix of create, update, delete."""
        (tmp_path / "new.py").write_text("new file")
        (tmp_path / "modified.py").write_text("modified content")
        hashes = _compute_file_hashes(str(tmp_path), ["new.py", "modified.py"])

        cached = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="",
            files={
                "modified.py": "sha256:old_hash",
                "deleted.py": "sha256:some_hash",
            },
        )

        operations, new_hashes, new_skipped = _compute_diff_operations(
            str(tmp_path), hashes, cached
        )

        types = {op["type"] for op in operations}
        filenames = {op["filename"] for op in operations}

        assert "write" in types
        assert "delete" in types
        assert "new.py" in filenames
        assert "modified.py" in filenames
        assert "deleted.py" in filenames
        assert len(new_skipped) == 0

    def test_skips_delete_when_file_exists_but_hash_failed(self, tmp_path: Path) -> None:
        """Should not delete files that exist but failed to hash."""
        # File exists on disk but not in current_hashes (simulating hash failure)
        (tmp_path / "exists.py").write_text("content")
        current_hashes: dict[str, str] = {}  # Empty = all hashes failed

        cached = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="",
            files={"exists.py": "sha256:old_hash"},  # Was synced before
        )

        operations, _, new_skipped = _compute_diff_operations(str(tmp_path), current_hashes, cached)

        # File exists, should not be deleted even if hash failed
        assert len(operations) == 0

    def test_deletes_truly_missing_files(self, tmp_path: Path) -> None:
        """Should delete files that are truly missing from disk."""
        # No file on disk, and not in current_hashes
        current_hashes: dict[str, str] = {}

        cached = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="",
            files={"truly_deleted.py": "sha256:old_hash"},
        )

        operations, _, new_skipped = _compute_diff_operations(str(tmp_path), current_hashes, cached)

        # File does not exist, should be deleted
        assert len(operations) == 1
        assert operations[0]["type"] == "delete"
        assert operations[0]["filename"] == "truly_deleted.py"

    def test_decodes_big5_files_for_upload(self, tmp_path: Path) -> None:
        """Should decode Big5 files instead of skipping them as binary."""
        content = "# 繁體中文註解\nprint('世界')\n"
        (tmp_path / "main.py").write_bytes(content.encode("big5"))
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        try:
            set_project_encoding("big5")
            operations, _, new_skipped = _compute_diff_operations(str(tmp_path), hashes, None)
            assert len(new_skipped) == 0
            assert len(operations) == 1
            assert operations[0]["type"] == "write"
            assert operations[0]["filename"] == "main.py"
            assert operations[0]["content"] == content
        finally:
            set_project_encoding(None)

    def test_decodes_gbk_files_for_upload(self, tmp_path: Path) -> None:
        """Should decode GBK files instead of skipping them as binary."""
        content = "# 这是简体中文注释\nprint('你好')\n"
        (tmp_path / "main.py").write_bytes(content.encode("gbk"))
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        try:
            set_project_encoding("gbk")
            operations, _, new_skipped = _compute_diff_operations(str(tmp_path), hashes, None)
            assert len(new_skipped) == 0
            assert len(operations) == 1
            assert operations[0]["type"] == "write"
            assert operations[0]["filename"] == "main.py"
            assert operations[0]["content"] == content
        finally:
            set_project_encoding(None)


class TestCloudSyncLogic:
    """Test cloud_sync_logic function."""

    def test_sync_uploads_files_incremental(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Should sync files using incremental update API."""
        # Create test files
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
            with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=None):
                with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                    result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["repo_id"] == "test-repo-id"
        assert result["files_created"] == 2
        assert result["files_updated"] == 0
        assert result["is_incremental"] is False  # No cache = full sync
        mock_repo_client.update_repo.assert_called_once()

    def test_sync_incremental_with_cache(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should use incremental sync when cache exists."""
        (tmp_path / "main.py").write_text("print('hello')")

        # Create cached state with same file
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="abc123",
            last_sync="",
            files={},  # Empty = all files are new
        )

        with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
            with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=cached):
                with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                    result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["is_incremental"] is True
        assert result["files_created"] == 1

    def test_sync_skips_unchanged_files(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should skip unchanged files in incremental sync."""
        (tmp_path / "main.py").write_text("print('hello')")
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="abc123",
            last_sync="",
            files=hashes.copy(),
        )

        with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
            with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=cached):
                with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                    result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["files_unchanged"] == 1
        assert result["files_created"] == 0
        assert result["files_updated"] == 0
        # update_repo should NOT be called when no changes
        mock_repo_client.update_repo.assert_not_called()

    def test_sync_force_ignores_cache(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should ignore cache when force=True."""
        (tmp_path / "main.py").write_text("print('hello')")
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="abc123",
            last_sync="",
            files=hashes.copy(),
        )

        with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
            with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=cached):
                with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                    result = cloud_sync_logic(mock_repo_client, str(tmp_path), force=True)

        assert result["is_incremental"] is False
        assert result["files_created"] == 1  # Treated as new

    def test_sync_returns_error_on_ensure_repo_failure(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Should return error when ensure_repo fails."""
        mock_repo_client.ensure_repo.side_effect = RuntimeError("API error")

        result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["repo_id"] is None
        assert "error" in result
        assert "API error" in result["error"]

    def test_sync_does_not_require_config_base_dir(self, tmp_path: Path) -> None:
        """Should work when RelaceConfig.base_dir is None (dynamic base_dir resolution)."""
        client = RelaceRepoClient(RelaceConfig(api_key="rlc-test-api-key", base_dir=None))
        with patch.object(client, "ensure_repo", side_effect=RuntimeError("API error")):
            result = cloud_sync_logic(client, str(tmp_path))

        assert result["repo_id"] is None
        assert result["repo_name"] == tmp_path.name
        assert "API error" in result.get("error", "")

    def test_sync_respects_file_limit(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should respect REPO_SYNC_MAX_FILES limit."""
        # Create many files
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")

        with patch("relace_mcp.tools.repo.sync.REPO_SYNC_MAX_FILES", 5):
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=None):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        # Should only process 5 files
        assert result["total_files"] == 5


class TestSyncState:
    """Test sync state management."""

    def test_compute_file_hash(self, tmp_path: Path) -> None:
        """Should compute SHA-256 hash."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        file_hash = compute_file_hash(test_file)

        assert file_hash is not None
        assert file_hash.startswith("sha256:")
        assert len(file_hash) == 7 + 64  # "sha256:" + 64 hex chars

    def test_compute_file_hash_missing_file(self, tmp_path: Path) -> None:
        """Should return None for missing file."""
        file_hash = compute_file_hash(tmp_path / "missing.py")
        assert file_hash is None

    def test_sync_state_to_dict(self) -> None:
        """Should serialize to dict."""
        state = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="2025-01-01T00:00:00Z",
            files={"main.py": "sha256:abc"},
        )

        data = state.to_dict()

        assert data["repo_id"] == "test-id"
        assert data["repo_head"] == "abc123"
        assert data["files"]["main.py"] == "sha256:abc"

    def test_sync_state_from_dict(self) -> None:
        """Should deserialize from dict."""
        data = {
            "repo_id": "test-id",
            "repo_head": "abc123",
            "last_sync": "2025-01-01T00:00:00Z",
            "files": {"main.py": "sha256:abc"},
        }

        state = SyncState.from_dict(data)

        assert state.repo_id == "test-id"
        assert state.repo_head == "abc123"
        assert state.files["main.py"] == "sha256:abc"

    def test_save_and_load_sync_state(self, tmp_path: Path) -> None:
        """Should save and load sync state."""
        # Override XDG state dir for test
        with patch("relace_mcp.tools.repo.state._STATE_DIR", tmp_path):
            state = SyncState(
                repo_id="test-id",
                repo_head="abc123",
                last_sync="",
                files={"main.py": "sha256:abc"},
            )

            save_sync_state("test-project", state)
            loaded = load_sync_state("test-project")

        assert loaded is not None
        assert loaded.repo_id == "test-id"
        assert loaded.files["main.py"] == "sha256:abc"

    def test_load_sync_state_missing(self, tmp_path: Path) -> None:
        """Should return None for missing state."""
        with patch("relace_mcp.tools.repo.state._STATE_DIR", tmp_path):
            loaded = load_sync_state("nonexistent-project")

        assert loaded is None


class TestCodeExtensions:
    """Test CODE_EXTENSIONS and SPECIAL_FILENAMES constants."""

    def test_common_extensions_included(self) -> None:
        """Should include common programming language extensions."""
        common = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp"}
        assert common.issubset(CODE_EXTENSIONS)

    def test_config_extensions_included(self) -> None:
        """Should include config file extensions."""
        config = {".json", ".yaml", ".yml", ".toml", ".xml"}
        assert config.issubset(CODE_EXTENSIONS)

    def test_special_filenames_included(self) -> None:
        """Should include special filenames."""
        special = {"dockerfile", "makefile", "gemfile"}
        assert special.issubset(SPECIAL_FILENAMES)


class TestSyncStateMigration:
    """Test backward compatibility for SyncState git fields."""

    def test_old_state_without_git_fields(self) -> None:
        """Should load old state without git_branch/git_head_sha without crashing."""
        old_data = {
            "repo_id": "test-id",
            "repo_head": "abc123",
            "last_sync": "2025-01-01T00:00:00Z",
            "files": {"main.py": "sha256:abc"},
            "skipped_files": [],
        }

        state = SyncState.from_dict(old_data)

        assert state.repo_id == "test-id"
        assert state.git_branch == ""
        assert state.git_head_sha == ""
        assert state.files["main.py"] == "sha256:abc"

    def test_new_state_with_git_fields(self) -> None:
        """Should correctly load new state with git fields."""
        new_data = {
            "repo_id": "test-id",
            "repo_head": "abc123",
            "last_sync": "2025-01-01T00:00:00Z",
            "git_branch": "main",
            "git_head_sha": "def456789",
            "files": {"main.py": "sha256:abc"},
            "skipped_files": [],
        }

        state = SyncState.from_dict(new_data)

        assert state.git_branch == "main"
        assert state.git_head_sha == "def456789"

    def test_to_dict_includes_git_fields(self) -> None:
        """Should serialize git fields to dict."""
        state = SyncState(
            repo_id="test-id",
            repo_head="abc123",
            last_sync="2025-01-01T00:00:00Z",
            git_branch="feature-x",
            git_head_sha="abc123def",
            files={},
        )

        data = state.to_dict()

        assert data["git_branch"] == "feature-x"
        assert data["git_head_sha"] == "abc123def"


class TestSyncStateCollisionDetection:
    """Test repo_name collision detection in sync state."""

    def test_load_rejects_mismatched_repo_name(self, tmp_path: Path) -> None:
        """Should return None when stored repo_name doesn't match requested name."""
        with patch("relace_mcp.tools.repo.state._STATE_DIR", tmp_path):
            # Save state for 'my.project'
            state = SyncState(
                repo_id="project-a-id",
                repo_head="abc",
                last_sync="",
                repo_name="my.project",
                files={},
            )
            save_sync_state("my.project", state)

            # Try to load with colliding name 'my_project' (maps to same file)
            loaded = load_sync_state("my_project")

        # Should reject because repo_name doesn't match
        assert loaded is None

    def test_load_accepts_matching_repo_name(self, tmp_path: Path) -> None:
        """Should accept state when repo_name matches."""
        with patch("relace_mcp.tools.repo.state._STATE_DIR", tmp_path):
            state = SyncState(
                repo_id="project-id",
                repo_head="abc",
                last_sync="",
                repo_name="my-project",
                files={},
            )
            save_sync_state("my-project", state)

            loaded = load_sync_state("my-project")

        assert loaded is not None
        assert loaded.repo_id == "project-id"
        assert loaded.repo_name == "my-project"

    def test_load_accepts_old_state_without_repo_name(self, tmp_path: Path) -> None:
        """Should accept old state files without repo_name for backward compat."""
        import json

        with patch("relace_mcp.tools.repo.state._STATE_DIR", tmp_path):
            # Manually create old-format state file without repo_name
            state_file = tmp_path / "my_project.json"
            tmp_path.mkdir(parents=True, exist_ok=True)
            state_file.write_text(
                json.dumps(
                    {
                        "repo_id": "old-id",
                        "repo_head": "abc",
                        "last_sync": "",
                        "files": {},
                        "skipped_files": [],
                    }
                )
            )

            loaded = load_sync_state("my_project")

        # Should accept (backward compat)
        assert loaded is not None
        assert loaded.repo_id == "old-id"
        assert loaded.repo_name == ""

    def test_save_sets_repo_name_automatically(self, tmp_path: Path) -> None:
        """Should automatically set repo_name when saving."""
        with patch("relace_mcp.tools.repo.state._STATE_DIR", tmp_path):
            state = SyncState(
                repo_id="test-id",
                repo_head="abc",
                last_sync="",
                files={},
            )
            # repo_name is initially empty
            assert state.repo_name == ""

            save_sync_state("my-project", state)

            # After save, state should have repo_name set
            assert state.repo_name == "my-project"

            # And the loaded state should also have it
            loaded = load_sync_state("my-project")
            assert loaded is not None
            assert loaded.repo_name == "my-project"


class TestGetCurrentGitInfo:
    """Test get_current_git_info function."""

    def test_returns_empty_for_non_git_dir(self, tmp_path: Path) -> None:
        """Should return empty strings for non-git directory."""
        branch, head = get_current_git_info(str(tmp_path))

        assert branch == ""
        assert head == ""

    def test_returns_branch_and_sha_in_git_repo(self, tmp_path: Path) -> None:
        """Should return branch name and HEAD SHA in git repo."""
        import subprocess

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        # Some environments enforce commit signing (commit.gpgsign=true), which can
        # cause commits to fail in CI/sandboxed runners without a configured GPG agent.
        commit = subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-m", "Initial"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert commit.returncode == 0, f"git commit failed: {commit.stderr}"

        branch, head = get_current_git_info(str(tmp_path))

        assert branch != ""
        assert len(head) == 40  # Full SHA


class TestRefChangedDetection:
    """Test git ref change detection in cloud_sync."""

    def test_ref_changed_triggers_safe_full_sync(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Should use safe_full sync when git HEAD changes."""
        (tmp_path / "main.py").write_text("print('hello')")
        hashes = _compute_file_hashes(str(tmp_path), ["main.py"])

        # Cached state with different HEAD
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="abc123",
            last_sync="",
            git_branch="main",
            git_head_sha="old_head_sha_123456789012345678901234",
            files=hashes.copy(),
        )

        # Mock git returning a different HEAD
        with patch("relace_mcp.tools.repo.sync.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "new_head_sha_987654321098765432109876")
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=cached):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["ref_changed"] is True
        assert result["sync_mode"] == "safe_full"
        assert result["is_incremental"] is False


class TestSafeSyncMode:
    """Test Safe Full sync mode behavior."""

    def test_ref_change_cleans_zombie_files(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Branch switch should delete zombie files from cloud.

        When git ref changes, files that existed in the old branch but not in the
        new branch should be deleted from cloud to prevent stale search results.
        This is the zombie file cleanup behavior.
        """
        # Only one file exists now (new branch)
        (tmp_path / "new.py").write_text("print('new')")

        # Cached state had a file that no longer exists (old branch)
        cached = SyncState(
            repo_id="test-repo-id",
            repo_head="abc123",
            last_sync="",
            git_branch="main",
            git_head_sha="old_head_sha_123456789012345678901234",
            files={"deleted.py": "sha256:old_hash"},
        )

        # Mock git returning a different HEAD → triggers safe_full with ref_changed
        with patch("relace_mcp.tools.repo.sync.get_current_git_info") as mock_git:
            mock_git.return_value = ("feature", "new_head_sha_987654321098765432109876")
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=cached):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["sync_mode"] == "safe_full"
        assert result["ref_changed"] is True
        # Zombie files should be DELETED (not suppressed) when ref changes
        assert result["deletes_suppressed"] == 0
        assert result["files_deleted"] == 1

        # Verify delete operation was sent to API
        call_args = mock_repo_client.update_repo.call_args
        operations = call_args[0][1]
        delete_ops = [op for op in operations if op["type"] == "delete"]
        assert len(delete_ops) == 1
        assert delete_ops[0]["filename"] == "deleted.py"

    def test_force_without_ref_change_suppresses_deletes(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """force=True without branch switch should suppress delete operations.

        This is a safety measure: user explicitly used force but not mirror,
        so we don't delete files. User can use mirror=True to clean up if needed.
        """
        # File exists
        (tmp_path / "exists.py").write_text("print('exists')")

        # force=True bypasses cache loading, so diff_state will be None
        # This means no delete operations will be computed
        with patch("relace_mcp.tools.repo.sync.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "head_sha_12345678901234567890123456")
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=None):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        result = cloud_sync_logic(mock_repo_client, str(tmp_path), force=True)

        assert result["sync_mode"] == "safe_full"
        # No ref_changed since this is a fresh sync (no cached state)
        assert result["ref_changed"] is False
        # No deletes computed because no cached state to compare against
        assert result["deletes_suppressed"] == 0
        assert result["files_deleted"] == 0


class TestMirrorSyncMode:
    """Test Mirror Full sync mode behavior."""

    def test_mirror_mode_uses_update_repo_files(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Mirror Full should use update_repo_files with type=files."""
        (tmp_path / "main.py").write_text("print('hello')")

        mock_repo_client.update_repo_files.return_value = {"repo_head": "new_head_123"}

        with patch("relace_mcp.tools.repo.sync.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "head_sha_123456789012345678901234567890")
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=None):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        result = cloud_sync_logic(
                            mock_repo_client, str(tmp_path), force=True, mirror=True
                        )

        assert result["sync_mode"] == "mirror_full"
        mock_repo_client.update_repo_files.assert_called_once()
        # update_repo should NOT be called in mirror mode
        mock_repo_client.update_repo.assert_not_called()

    def test_mirror_requires_force(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Mirror mode should only activate when force=True."""
        (tmp_path / "main.py").write_text("print('hello')")

        with patch("relace_mcp.tools.repo.sync.get_current_git_info") as mock_git:
            mock_git.return_value = ("main", "head_sha_123456789012345678901234567890")
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=None):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        # mirror=True but force=False → should NOT be mirror_full
                        result = cloud_sync_logic(
                            mock_repo_client, str(tmp_path), force=False, mirror=True
                        )

        # Without force, should be safe_full (no cache)
        assert result["sync_mode"] == "safe_full"


class TestSyncDebugFields:
    """Test debug fields in cloud_sync return value."""

    def test_returns_git_info(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should return local git info in result."""
        (tmp_path / "main.py").write_text("print('hello')")

        with patch("relace_mcp.tools.repo.sync.get_current_git_info") as mock_git:
            mock_git.return_value = ("feature-x", "abc123def456789012345678901234567890")
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                with patch("relace_mcp.tools.repo.sync.load_sync_state", return_value=None):
                    with patch("relace_mcp.tools.repo.sync.save_sync_state"):
                        result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["local_git_branch"] == "feature-x"
        assert result["local_git_head"] == "abc123de"  # First 8 chars
        assert result["ref_changed"] is False  # No cache to compare
        assert result["sync_mode"] == "safe_full"
        assert result["deletes_suppressed"] == 0
