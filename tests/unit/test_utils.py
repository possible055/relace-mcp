"""Tests for relace_mcp.utils module."""

from pathlib import Path

import pytest

from relace_mcp.utils import resolve_repo_path


class TestResolveRepoPath:
    """Test resolve_repo_path function."""

    def test_repo_root(self, tmp_path: Path) -> None:
        """Test /repo maps to base_dir."""
        result = resolve_repo_path("/repo", str(tmp_path))
        assert result == str(tmp_path)

    def test_repo_root_with_slash(self, tmp_path: Path) -> None:
        """Test /repo/ maps to base_dir."""
        result = resolve_repo_path("/repo/", str(tmp_path))
        assert result == str(tmp_path)

    def test_repo_subpath(self, tmp_path: Path) -> None:
        """Test /repo/subdir maps correctly."""
        (tmp_path / "src").mkdir()
        result = resolve_repo_path("/repo/src", str(tmp_path))
        assert result == str(tmp_path / "src")

    def test_repo_nested_subpath(self, tmp_path: Path) -> None:
        """Test /repo/a/b/c maps correctly."""
        (tmp_path / "a" / "b").mkdir(parents=True)
        result = resolve_repo_path("/repo/a/b/c.py", str(tmp_path))
        assert result == str(tmp_path / "a" / "b" / "c.py")

    def test_relative_path(self, tmp_path: Path) -> None:
        """Test relative path is resolved against base_dir."""
        result = resolve_repo_path("src/main.py", str(tmp_path))
        assert result == str((tmp_path / "src" / "main.py").resolve())

    def test_absolute_path_passthrough(self, tmp_path: Path) -> None:
        """Test absolute path is passed through."""
        # Use a non-existent path to avoid symlink resolution issues
        result = resolve_repo_path("/nonexistent/absolute/path", str(tmp_path))
        # On Windows, Path.resolve() adds drive letter prefix to absolute paths
        expected = str(Path("/nonexistent/absolute/path").resolve())
        assert result == expected


class TestResolveRepoPathSecurity:
    """Security tests for resolve_repo_path."""

    def test_normalizes_repo_double_slash(self, tmp_path: Path) -> None:
        """Test /repo//etc/passwd is normalized to base_dir/etc/passwd (not /etc/passwd)."""
        result = resolve_repo_path("/repo//etc/passwd", str(tmp_path))
        # Should be normalized to base_dir/etc/passwd, NOT /etc/passwd
        assert result == str(tmp_path / "etc" / "passwd")
        assert result.startswith(str(tmp_path))

    def test_normalizes_repo_triple_slash(self, tmp_path: Path) -> None:
        """Test /repo///etc/passwd is normalized to base_dir/etc/passwd (not /etc/passwd)."""
        result = resolve_repo_path("/repo///etc/passwd", str(tmp_path))
        # Should be normalized to base_dir/etc/passwd, NOT /etc/passwd
        assert result == str(tmp_path / "etc" / "passwd")
        assert result.startswith(str(tmp_path))

    def test_blocks_path_traversal(self, tmp_path: Path) -> None:
        """Test /repo/../etc/passwd path traversal is blocked."""
        with pytest.raises(ValueError, match="Path escapes base_dir"):
            resolve_repo_path("/repo/../etc/passwd", str(tmp_path))

    def test_blocks_relative_path_traversal(self, tmp_path: Path) -> None:
        """Test ../etc/passwd path traversal is blocked."""
        with pytest.raises(ValueError, match="Path escapes base_dir"):
            resolve_repo_path("../etc/passwd", str(tmp_path))

    def test_blocks_nested_path_traversal(self, tmp_path: Path) -> None:
        """Test /repo/a/../../etc/passwd path traversal is blocked."""
        (tmp_path / "a").mkdir()
        with pytest.raises(ValueError, match="Path escapes base_dir"):
            resolve_repo_path("/repo/a/../../etc/passwd", str(tmp_path))

    def test_allows_internal_double_slash(self, tmp_path: Path) -> None:
        """Test /repo/a//b (internal double slash) is normalized."""
        (tmp_path / "a" / "b").mkdir(parents=True)
        result = resolve_repo_path("/repo/a//b", str(tmp_path))
        assert result == str(tmp_path / "a" / "b")

    def test_blocks_relative_when_disallowed(self, tmp_path: Path) -> None:
        """Test relative path is rejected when allow_relative=False."""
        with pytest.raises(ValueError, match="Relative path not allowed"):
            resolve_repo_path("src/main.py", str(tmp_path), allow_relative=False)

    def test_blocks_absolute_when_disallowed(self, tmp_path: Path) -> None:
        """Test absolute path is rejected when allow_absolute=False."""
        with pytest.raises(ValueError, match="Absolute path not allowed"):
            resolve_repo_path("/usr/bin/python", str(tmp_path), allow_absolute=False)

    def test_blocks_absolute_outside_base_dir_when_enforced(self, tmp_path: Path) -> None:
        """Test absolute paths are rejected when require_within_base_dir=True."""
        outside = tmp_path.parent / "outside.py"
        with pytest.raises(ValueError, match="Path escapes base_dir"):
            resolve_repo_path(str(outside), str(tmp_path), require_within_base_dir=True)

    def test_allows_absolute_inside_base_dir_when_enforced(self, tmp_path: Path) -> None:
        """Test absolute path inside base_dir is allowed when enforce flag is set."""
        inside = tmp_path / "inside.py"
        result = resolve_repo_path(str(inside), str(tmp_path), require_within_base_dir=True)
        assert result == str(inside.resolve())


class TestResolveRepoPathEdgeCases:
    """Edge case tests for resolve_repo_path."""

    def test_repo_with_only_slashes(self, tmp_path: Path) -> None:
        """Test /repo//// normalizes to base_dir."""
        result = resolve_repo_path("/repo////", str(tmp_path))
        assert result == str(tmp_path)

    def test_repofake_not_matched(self, tmp_path: Path) -> None:
        """Test /repofake is not treated as /repo prefix."""
        # /repofake is an absolute path, should pass through
        result = resolve_repo_path("/repofake/etc", str(tmp_path))
        # On Windows, Path.resolve() adds drive letter prefix
        expected = str(Path("/repofake/etc").resolve())
        assert result == expected

    def test_repo_lowercase_only(self, tmp_path: Path) -> None:
        """Test /REPO is not treated as /repo (case sensitive)."""
        result = resolve_repo_path("/REPO/src", str(tmp_path))
        # On Windows, Path.resolve() adds drive letter prefix
        expected = str(Path("/REPO/src").resolve())
        assert result == expected  # Passed through as absolute path
