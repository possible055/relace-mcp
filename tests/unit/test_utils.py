from pathlib import Path

import pytest

from relace_mcp.utils import resolve_repo_path, validate_file_path


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


class TestResolveRepoPathSymlinks:
    """Symlink handling tests for resolve_repo_path."""

    def test_symlink_within_base_dir_allowed(self, tmp_path: Path) -> None:
        """Test symlink pointing within base_dir is allowed."""
        # Create real directory and file
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_file = real_dir / "file.txt"
        real_file.write_text("content")

        # Create symlink within base_dir
        link = tmp_path / "link"
        link.symlink_to(real_dir)

        # Access via symlink should work
        result = resolve_repo_path("/repo/link/file.txt", str(tmp_path))
        assert "file.txt" in result

    def test_symlink_escaping_base_dir_blocked(self, tmp_path: Path) -> None:
        """Test symlink pointing outside base_dir is blocked."""
        import tempfile

        # Create directory outside base_dir
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "secret.txt"
            outside_file.write_text("secret")

            # Create symlink inside base_dir pointing outside
            link = tmp_path / "escape_link"
            link.symlink_to(outside_dir)

            # Access via symlink should be blocked
            with pytest.raises(ValueError, match="Path escapes base_dir"):
                resolve_repo_path("/repo/escape_link/secret.txt", str(tmp_path))

    def test_existing_path_uses_samefile(self, tmp_path: Path) -> None:
        """Test that existing paths use os.path.samefile for comparison."""
        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Access should work for existing files
        result = resolve_repo_path("/repo/test.txt", str(tmp_path))
        assert result == str(test_file.resolve())


class TestValidateFilePathExtraPaths:
    """Tests for validate_file_path with extra_paths."""

    def test_path_within_base_dir(self, tmp_path: Path) -> None:
        """Path inside base_dir passes without extra_paths."""
        f = tmp_path / "file.txt"
        f.write_text("ok")
        result = validate_file_path(str(f), str(tmp_path))
        assert result == f.resolve()

    def test_path_within_extra_path(self, tmp_path: Path) -> None:
        """Path outside base_dir but inside extra_paths passes."""
        base = tmp_path / "project"
        base.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        f = extra / "config.md"
        f.write_text("rules")

        result = validate_file_path(str(f), str(base), extra_paths=[str(extra)])
        assert result == f.resolve()

    def test_path_outside_all_rejected(self, tmp_path: Path) -> None:
        """Path outside both base_dir and extra_paths is rejected."""
        base = tmp_path / "project"
        base.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        outside = tmp_path / "forbidden" / "secret.txt"

        with pytest.raises(RuntimeError, match="Access denied"):
            validate_file_path(str(outside), str(base), extra_paths=[str(extra)])

    def test_extra_paths_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal out of extra_paths is blocked."""
        base = tmp_path / "project"
        base.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()

        # Try to escape both base_dir and extra_paths via ../../
        traversal = str(extra / ".." / ".." / "etc" / "passwd")
        with pytest.raises(RuntimeError, match="Access denied"):
            validate_file_path(traversal, str(base), extra_paths=[str(extra)])

    def test_relative_resolves_to_base_only(self, tmp_path: Path) -> None:
        """Relative paths always resolve against base_dir, not extra_paths."""
        base = tmp_path / "project"
        base.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "readme.md").write_text("hi")

        # "readme.md" resolves to base/readme.md (within base_dir), not extra/readme.md
        result = validate_file_path("readme.md", str(base), extra_paths=[str(extra)])
        assert result == (base / "readme.md").resolve()
        assert str(result).startswith(str(base))

    def test_multiple_extra_paths(self, tmp_path: Path) -> None:
        """Multiple extra_paths are checked in order."""
        base = tmp_path / "project"
        base.mkdir()
        extra1 = tmp_path / "extra1"
        extra1.mkdir()
        extra2 = tmp_path / "extra2"
        extra2.mkdir()
        f = extra2 / "deep" / "file.txt"
        f.parent.mkdir(parents=True)
        f.write_text("ok")

        result = validate_file_path(str(f), str(base), extra_paths=[str(extra1), str(extra2)])
        assert result == f.resolve()

    def test_empty_extra_paths(self, tmp_path: Path) -> None:
        """Empty extra_paths behaves identically to original."""
        f = tmp_path / "file.txt"
        f.write_text("ok")
        result = validate_file_path(str(f), str(tmp_path), extra_paths=())
        assert result == f.resolve()

        outside = tmp_path.parent / "outside.txt"
        with pytest.raises(RuntimeError, match="Access denied"):
            validate_file_path(str(outside), str(tmp_path), extra_paths=())
