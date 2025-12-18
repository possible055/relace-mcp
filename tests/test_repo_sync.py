"""Tests for cloud_sync logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients.repo import RelaceRepoClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.repo.sync import (
    CODE_EXTENSIONS,
    SPECIAL_FILENAMES,
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
    client.upload_file.return_value = {"status": "ok"}
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


class TestCloudSyncLogic:
    """Test cloud_sync_logic function."""

    def test_sync_uploads_files(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should upload files to cloud."""
        # Create test files
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
            result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["repo_id"] == "test-repo-id"
        assert result["files_uploaded"] == 2
        assert result["files_skipped"] == 0
        assert mock_repo_client.upload_file.call_count == 2

    def test_sync_handles_upload_errors(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should handle and report upload errors."""
        (tmp_path / "main.py").write_text("print('hello')")

        mock_repo_client.upload_file.side_effect = Exception("Upload failed")

        with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
            result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["files_uploaded"] == 0
        assert result["files_skipped"] == 1
        assert len(result["errors"]) > 0
        assert "Upload failed" in result["errors"][0]

    def test_sync_returns_error_on_ensure_repo_failure(
        self, tmp_path: Path, mock_repo_client: MagicMock
    ) -> None:
        """Should return error when ensure_repo fails."""
        mock_repo_client.ensure_repo.side_effect = RuntimeError("API error")

        result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        assert result["repo_id"] is None
        assert "error" in result
        assert "API error" in result["error"]

    def test_sync_respects_file_limit(self, tmp_path: Path, mock_repo_client: MagicMock) -> None:
        """Should respect REPO_SYNC_MAX_FILES limit."""
        # Create many files
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")

        with patch("relace_mcp.tools.repo.sync.REPO_SYNC_MAX_FILES", 5):
            with patch("relace_mcp.tools.repo.sync._get_git_tracked_files", return_value=None):
                result = cloud_sync_logic(mock_repo_client, str(tmp_path))

        # Should only upload 5 files
        assert result["total_files"] == 5
        assert mock_repo_client.upload_file.call_count == 5


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
