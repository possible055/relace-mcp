"""Tests for dynamic base_dir resolution with MCP Roots support."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from relace_mcp.config.base_dir import (
    find_git_root,
    resolve_base_dir,
    select_best_root,
    uri_to_path,
    validate_base_dir,
)


class TestValidateBaseDir:
    def test_valid_directory(self, tmp_path: Path) -> None:
        assert validate_base_dir(str(tmp_path)) is True

    def test_non_existent_path(self) -> None:
        assert validate_base_dir("/non/existent/path/at/all") is False

    def test_file_instead_of_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.touch()
        assert validate_base_dir(str(f)) is False


class TestUriToPath:
    def test_simple_file_uri(self) -> None:
        result = uri_to_path("file:///home/user/project")
        # On Windows url2pathname uses backslashes; on POSIX it uses forward slashes
        if os.name == "nt":
            # Windows: strips leading slash, so result is '\home\user\project' without drive
            assert result == "\\home\\user\\project"
        else:
            assert result == "/home/user/project"

    def test_uri_with_spaces(self) -> None:
        result = uri_to_path("file:///path/with%20spaces")
        if os.name == "nt":
            assert result == "\\path\\with spaces"
        else:
            assert result == "/path/with spaces"

    def test_windows_style_uri(self) -> None:
        # Windows paths in URI form
        result = uri_to_path("file:///C:/Users/test/project")
        # On Linux, url2pathname('/C:/...') -> '/C:/...'
        # On Windows, it would be 'C:\\Users\\...'
        # The test should be flexible
        assert "C:" in result and "Users" in result

    def test_unc_style_uri(self) -> None:
        # UNC paths in URI form: file://server/share/folder
        result = uri_to_path("file://server/share/folder")
        # On POSIX: //server/share/folder
        # On Windows: \\server\share\folder
        assert "server" in result and "share" in result

    def test_non_file_scheme(self) -> None:
        # Should return unquoted string if not file://
        assert uri_to_path("http://example.com/path") == "http://example.com/path"
        assert uri_to_path("/absolute/path") == "/absolute/path"


class TestFindGitRoot:
    def test_finds_git_root(self, tmp_path: Path) -> None:
        # Create nested structure with .git at root
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        nested = tmp_path / "src" / "deep" / "nested"
        nested.mkdir(parents=True)

        result = find_git_root(str(nested))
        assert result == tmp_path

    def test_returns_none_when_no_git(self, tmp_path: Path) -> None:
        nested = tmp_path / "src" / "deep"
        nested.mkdir(parents=True)

        result = find_git_root(str(nested))
        assert result is None


class TestSelectBestRoot:
    def test_prefers_git_root(self, tmp_path: Path) -> None:
        # Create two roots, one with .git
        root1 = tmp_path / "project1"
        root2 = tmp_path / "project2"
        root1.mkdir()
        root2.mkdir()
        (root2 / ".git").mkdir()

        roots = [
            MagicMock(uri=f"file://{root1}", name="Project 1"),
            MagicMock(uri=f"file://{root2}", name="Project 2"),
        ]

        result = select_best_root(roots)
        assert result == str(root2)

    def test_prefers_pyproject_toml(self, tmp_path: Path) -> None:
        root1 = tmp_path / "project1"
        root2 = tmp_path / "project2"
        root1.mkdir()
        root2.mkdir()
        (root2 / "pyproject.toml").touch()

        roots = [
            MagicMock(uri=f"file://{root1}", name="Project 1"),
            MagicMock(uri=f"file://{root2}", name="Project 2"),
        ]

        result = select_best_root(roots)
        assert result == str(root2)

    def test_falls_back_to_first_root(self, tmp_path: Path) -> None:
        root1 = tmp_path / "project1"
        root2 = tmp_path / "project2"
        root1.mkdir()
        root2.mkdir()

        roots = [
            MagicMock(uri=f"file://{root1}", name="Project 1"),
            MagicMock(uri=f"file://{root2}", name="Project 2"),
        ]

        result = select_best_root(roots)
        assert result == str(root1)

    def test_skips_invalid_roots(self, tmp_path: Path) -> None:
        root1 = tmp_path / "invalid_file"
        root1.touch()
        root2 = tmp_path / "valid_dir"
        root2.mkdir()

        roots = [
            MagicMock(uri=f"file://{root1}", name="Invalid"),
            MagicMock(uri=f"file://{root2}", name="Valid"),
        ]

        result = select_best_root(roots)
        assert result == str(root2.resolve())


class TestResolveBaseDir:
    @pytest.mark.asyncio
    async def test_uses_config_base_dir_when_set(self) -> None:
        """Explicit config takes highest priority."""
        # On Windows, Path.resolve() adds drive letter, so we use a real temp path
        # or check normalized paths
        base_dir, source = await resolve_base_dir("/explicit/path", ctx=None)
        # Path.resolve() will convert to platform-specific format with drive on Windows
        # The key is that it should be resolved from the input
        expected = str(Path("/explicit/path").resolve())
        assert base_dir == expected
        assert source == "RELACE_BASE_DIR"

    @pytest.mark.asyncio
    async def test_uses_single_mcp_root(self, tmp_path: Path) -> None:
        """Single MCP Root is used when config is None."""
        ctx = MagicMock()
        ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{tmp_path}", name="Test Project")]
        )

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(tmp_path)
        assert "MCP Root" in source

    @pytest.mark.asyncio
    async def test_uses_heuristic_for_multiple_roots(self, tmp_path: Path) -> None:
        """Multiple MCP Roots trigger heuristic selection."""
        root1 = tmp_path / "project1"
        root2 = tmp_path / "project2"
        root1.mkdir()
        root2.mkdir()
        (root2 / ".git").mkdir()

        ctx = MagicMock()
        ctx.list_roots = AsyncMock(
            return_value=[
                MagicMock(uri=f"file://{root1}", name="Project 1"),
                MagicMock(uri=f"file://{root2}", name="Project 2 (git)"),
            ]
        )

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(root2)
        assert "selected from 2" in source

    @pytest.mark.asyncio
    async def test_falls_back_to_git_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to Git root when MCP Roots unavailable."""
        # Setup: create git repo structure
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        cwd = tmp_path / "src"
        cwd.mkdir()

        monkeypatch.chdir(cwd)

        ctx = MagicMock()
        ctx.list_roots = AsyncMock(return_value=[])  # Empty roots

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(tmp_path)
        assert "Git root" in source

    @pytest.mark.asyncio
    async def test_falls_back_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to cwd when no Git repo found."""
        monkeypatch.chdir(tmp_path)

        ctx = MagicMock()
        ctx.list_roots = AsyncMock(return_value=[])

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(tmp_path)
        assert "cwd" in source

    @pytest.mark.asyncio
    async def test_handles_ctx_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handles ctx=None gracefully (e.g., during startup)."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        base_dir, source = await resolve_base_dir(None, ctx=None)
        assert base_dir == str(tmp_path)
        assert "Git root" in source

    @pytest.mark.asyncio
    async def test_handles_list_roots_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gracefully handles exceptions from list_roots."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        ctx = MagicMock()
        ctx.list_roots = AsyncMock(side_effect=Exception("Client does not support roots"))

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(tmp_path)
        assert "Git root" in source

    @pytest.mark.asyncio
    async def test_single_invalid_mcp_root_falls_back_to_git_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Single MCP Root may be invalid; should fall back to Git root."""
        (tmp_path / ".git").mkdir()
        cwd = tmp_path / "src"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        invalid_root = tmp_path / "does-not-exist"
        ctx = MagicMock()
        ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{invalid_root}", name="Invalid Root")]
        )

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(tmp_path)
        assert "Git root" in source

    @pytest.mark.asyncio
    async def test_multiple_invalid_mcp_roots_falls_back_to_git_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple MCP Roots may all be invalid; should fall back to Git root."""
        (tmp_path / ".git").mkdir()
        cwd = tmp_path / "src"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        invalid_root1 = tmp_path / "does-not-exist-1"
        invalid_root2 = tmp_path / "does-not-exist-2"
        ctx = MagicMock()
        ctx.list_roots = AsyncMock(
            return_value=[
                MagicMock(uri=f"file://{invalid_root1}", name="Invalid 1"),
                MagicMock(uri=f"file://{invalid_root2}", name="Invalid 2"),
            ]
        )

        base_dir, source = await resolve_base_dir(None, ctx)
        assert base_dir == str(tmp_path)
        assert "Git root" in source

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
    def test_validate_base_dir_rejects_non_traversable_directory(self, tmp_path: Path) -> None:
        """Directory without execute/traverse permission should be invalid."""
        d = tmp_path / "no_traverse"
        d.mkdir()
        try:
            d.chmod(0o444)  # read-only, no execute
            assert validate_base_dir(str(d)) is False
        finally:
            # Ensure cleanup is possible even if the assertion fails
            d.chmod(0o755)
