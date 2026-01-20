import shutil
from pathlib import Path

import pytest

from relace_mcp.tools.apply.file_io import set_project_encoding
from relace_mcp.tools.search._impl import (
    MAX_TOOL_RESULT_CHARS,
    bash_handler,
    estimate_context_size,
    glob_handler,
    grep_search_handler,
    map_repo_path,
    truncate_for_context,
    view_directory_handler,
    view_file_handler,
)
from relace_mcp.tools.search.schemas import GrepSearchParams
from relace_mcp.utils import validate_file_path


class TestMapRepoPath:
    """Test /repo path mapping."""

    def test_maps_repo_root(self, tmp_path: Path) -> None:
        """Should map /repo to base_dir."""
        result = map_repo_path("/repo", str(tmp_path))
        assert result == str(tmp_path)

    def test_maps_repo_root_with_slash(self, tmp_path: Path) -> None:
        """Should map /repo/ to base_dir."""
        result = map_repo_path("/repo/", str(tmp_path))
        assert result == str(tmp_path)

    def test_maps_repo_subpath(self, tmp_path: Path) -> None:
        """Should map /repo/src/file.py to base_dir/src/file.py."""
        result = map_repo_path("/repo/src/file.py", str(tmp_path))
        assert result == str(tmp_path / "src" / "file.py")

    def test_passes_through_absolute_path(self, tmp_path: Path) -> None:
        """Non-/repo absolute paths should pass through unchanged."""
        result = map_repo_path("/other/path", str(tmp_path))
        # On Windows, Path.resolve() adds drive letter prefix
        expected = str(Path("/other/path").resolve())
        assert result == expected

    def test_resolves_relative_path(self, tmp_path: Path) -> None:
        """Relative paths should be resolved against base_dir."""
        result = map_repo_path("src/file.py", str(tmp_path))
        # Now relative paths are resolved to absolute paths
        assert result == str((tmp_path / "src" / "file.py").resolve())


class TestValidatePath:
    """Test path validation security."""

    def test_valid_path_within_base(self, tmp_path: Path) -> None:
        """Should accept paths within base_dir."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        result = validate_file_path(str(test_file), str(tmp_path), allow_empty=True)
        assert result == test_file.resolve()

    def test_blocks_path_traversal(self, tmp_path: Path) -> None:
        """Should block path traversal attempts."""
        outside_path = tmp_path.parent / "outside.py"
        with pytest.raises(RuntimeError, match="outside allowed directory"):
            validate_file_path(str(outside_path), str(tmp_path), allow_empty=True)

    def test_blocks_traversal_with_dots(self, tmp_path: Path) -> None:
        """Should block ../.. traversal."""
        traversal = str(tmp_path / ".." / ".." / "etc" / "passwd")
        with pytest.raises(RuntimeError, match="outside allowed directory"):
            validate_file_path(traversal, str(tmp_path), allow_empty=True)


class TestViewFileHandler:
    """Test view_file tool handler."""

    def test_reads_file_with_line_numbers(self, tmp_path: Path) -> None:
        """Should read file and add line numbers."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        result = view_file_handler("/repo/test.py", [1, 3], str(tmp_path))
        assert "1 line1" in result
        assert "2 line2" in result
        assert "3 line3" in result

    def test_truncates_at_range_end(self, tmp_path: Path) -> None:
        """Should show truncation message when not at EOF."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\n")

        result = view_file_handler("/repo/test.py", [1, 2], str(tmp_path))
        assert "1 line1" in result
        assert "2 line2" in result
        assert "truncated" in result

    def test_handles_negative_one_end(self, tmp_path: Path) -> None:
        """Should read to EOF when end is -1."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        result = view_file_handler("/repo/test.py", [2, -1], str(tmp_path))
        assert "2 line2" in result
        assert "3 line3" in result
        assert "truncated" not in result

    def test_returns_error_for_missing_file(self, tmp_path: Path) -> None:
        """Should return error for non-existent file."""
        result = view_file_handler("/repo/missing.py", [1, 100], str(tmp_path))
        assert "Error" in result
        assert "not found" in result.lower()

    def test_returns_error_for_directory(self, tmp_path: Path) -> None:
        """Should return error when path is a directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = view_file_handler("/repo/subdir", [1, 100], str(tmp_path))
        assert "Error" in result
        assert "Not a file" in result

    def test_empty_range_has_no_truncation_notice(self, tmp_path: Path) -> None:
        """Empty ranges should not show a confusing truncation message."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        # Out-of-bounds range produces no numbered lines.
        result = view_file_handler("/repo/test.py", [100, 200], str(tmp_path))
        assert result.strip() == ""
        assert "truncated" not in result.lower()

    def test_reads_big5_encoded_file(self, tmp_path: Path) -> None:
        """Should correctly render Big5-encoded files."""
        big5_file = tmp_path / "big5_file.py"
        content = "# 繁體中文註解\nprint('世界')\n"
        big5_file.write_bytes(content.encode("big5"))

        try:
            set_project_encoding("big5")
            result = view_file_handler("/repo/big5_file.py", [1, 2], str(tmp_path))
            assert "繁體中文註解" in result
            assert "print('世界')" in result
        finally:
            set_project_encoding(None)

    def test_reads_gbk_encoded_file(self, tmp_path: Path) -> None:
        """Should correctly render GBK-encoded files."""
        gbk_file = tmp_path / "gbk_file.py"
        content = "# 这是简体中文注释\nprint('你好')\n"
        gbk_file.write_bytes(content.encode("gbk"))

        try:
            set_project_encoding("gbk")
            result = view_file_handler("/repo/gbk_file.py", [1, 2], str(tmp_path))
            assert "这是简体中文注释" in result
            assert "print('你好')" in result
        finally:
            set_project_encoding(None)


class TestViewDirectoryHandler:
    """Test view_directory tool handler."""

    def test_lists_files_and_dirs(self, tmp_path: Path) -> None:
        """Should list files and directories."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.txt").write_text("content")

        result = view_directory_handler("/repo", False, str(tmp_path))
        assert "file1.txt" in result
        assert "subdir/" in result

    def test_excludes_hidden_by_default(self, tmp_path: Path) -> None:
        """Should exclude hidden files by default."""
        (tmp_path / ".hidden").write_text("content")
        (tmp_path / "visible.txt").write_text("content")

        result = view_directory_handler("/repo", False, str(tmp_path))
        assert ".hidden" not in result
        assert "visible.txt" in result

    def test_includes_hidden_when_requested(self, tmp_path: Path) -> None:
        """Should include hidden files when include_hidden=True."""
        (tmp_path / ".hidden").write_text("content")
        (tmp_path / "visible.txt").write_text("content")

        result = view_directory_handler("/repo", True, str(tmp_path))
        assert ".hidden" in result
        assert "visible.txt" in result

    def test_returns_error_for_missing_dir(self, tmp_path: Path) -> None:
        """Should return error for non-existent directory."""
        result = view_directory_handler("/repo/missing", False, str(tmp_path))
        assert "Error" in result

    def test_does_not_traverse_symlink_directories(self, tmp_path: Path) -> None:
        """Symlinked directories should not be traversed (prevents escape from base_dir)."""
        outside = tmp_path.parent / f"outside_dir_{tmp_path.name}"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        try:
            (tmp_path / "link").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as e:
            pytest.skip(f"symlink is not supported in this environment: {e!r}")

        result = view_directory_handler("/repo", False, str(tmp_path))
        assert "link" in result
        assert "secret.txt" not in result

    def test_respects_gitignore_file(self, tmp_path: Path) -> None:
        """Should exclude files and directories matching .gitignore patterns."""
        (tmp_path / ".gitignore").write_text("ignored_dir/\nignored.txt\n")
        (tmp_path / "ignored_dir").mkdir()
        (tmp_path / "ignored_dir" / "file.py").write_text("ignored")
        (tmp_path / "ignored.txt").write_text("ignored")
        (tmp_path / "visible.txt").write_text("visible")

        result = view_directory_handler("/repo", False, str(tmp_path))
        assert "visible.txt" in result
        assert "ignored_dir" not in result
        assert "ignored.txt" not in result

    def test_respects_gitignore_for_subdirectory_listing(self, tmp_path: Path) -> None:
        """Should apply .gitignore rules when listing a subdirectory."""
        (tmp_path / ".gitignore").write_text("sub/ignored.txt\n")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "ignored.txt").write_text("ignored")
        (tmp_path / "sub" / "visible.txt").write_text("visible")

        result = view_directory_handler("/repo/sub", False, str(tmp_path))
        assert "visible.txt" in result
        assert "ignored.txt" not in result


class TestGrepSearchHandler:
    """Test grep_search tool handler."""

    def test_finds_pattern_in_files(self, tmp_path: Path) -> None:
        """Should find pattern matches."""
        (tmp_path / "test.py").write_text("def hello():\n    print('world')\n")

        params = GrepSearchParams(
            query="hello",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "hello" in result
        assert "test.py" in result

    def test_case_insensitive_search(self, tmp_path: Path) -> None:
        """Should support case-insensitive search."""
        (tmp_path / "test.py").write_text("HELLO world\n")

        params = GrepSearchParams(
            query="hello",
            case_sensitive=False,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "HELLO" in result or "hello" in result.lower()

    def test_no_matches_returns_message(self, tmp_path: Path) -> None:
        """Should return 'No matches' when nothing found."""
        (tmp_path / "test.py").write_text("nothing here\n")

        params = GrepSearchParams(
            query="xyz123abc",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "No matches" in result

    def test_finds_non_ascii_in_big5_file_python_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-ASCII queries should work on Big5 files via Python fallback."""
        big5_file = tmp_path / "test.py"
        content = "# 繁體中文註解\nprint('世界')\n"
        big5_file.write_bytes(content.encode("big5"))

        try:
            set_project_encoding("big5")

            # Force ripgrep path to fail so handler uses Python fallback deterministically.
            import relace_mcp.tools.search._impl.grep_search as grep_mod

            def _raise(*_args: object, **_kwargs: object) -> object:
                raise FileNotFoundError("rg unavailable")

            monkeypatch.setattr(grep_mod.subprocess, "run", _raise)

            params = GrepSearchParams(
                query="繁體中文",
                case_sensitive=True,
                include_pattern=None,
                exclude_pattern=None,
                base_dir=str(tmp_path),
            )
            result = grep_search_handler(params)
            assert "test.py" in result
            assert "繁體中文" in result
        finally:
            set_project_encoding(None)

    def test_finds_non_ascii_in_gbk_file_python_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-ASCII queries should work on GBK files via Python fallback."""
        gbk_file = tmp_path / "test.py"
        content = "# 这是简体中文注释\nprint('你好')\n"
        gbk_file.write_bytes(content.encode("gbk"))

        try:
            set_project_encoding("gbk")

            import relace_mcp.tools.search._impl.grep_search as grep_mod

            def _raise(*_args: object, **_kwargs: object) -> object:
                raise FileNotFoundError("rg unavailable")

            monkeypatch.setattr(grep_mod.subprocess, "run", _raise)

            params = GrepSearchParams(
                query="简体中文",
                case_sensitive=True,
                include_pattern=None,
                exclude_pattern=None,
                base_dir=str(tmp_path),
            )
            result = grep_search_handler(params)
            assert "test.py" in result
            assert "简体中文" in result
        finally:
            set_project_encoding(None)

    def test_does_not_follow_symlink_files_python_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Python fallback should not follow file symlinks (prevents base_dir escape)."""
        outside = tmp_path.parent / f"outside_file_{tmp_path.name}.txt"
        outside.write_text("SECRET_PATTERN\n")
        try:
            (tmp_path / "link.txt").symlink_to(outside)
        except (OSError, NotImplementedError) as e:
            pytest.skip(f"symlink is not supported in this environment: {e!r}")

        # Force ripgrep path to fail so handler uses Python fallback deterministically.
        import relace_mcp.tools.search._impl.grep_search as grep_mod

        def _raise(*_args: object, **_kwargs: object) -> object:
            raise FileNotFoundError("rg unavailable")

        monkeypatch.setattr(grep_mod.subprocess, "run", _raise)

        params = GrepSearchParams(
            query="SECRET_PATTERN",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "No matches" in result

    def test_python_fallback_respects_gitignore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Python fallback should respect .gitignore patterns."""
        (tmp_path / ".gitignore").write_text("ignored_dir/\n")
        ignored_dir = tmp_path / "ignored_dir"
        ignored_dir.mkdir()
        (ignored_dir / "secret.py").write_text("HIDDEN_PATTERN\n")
        (tmp_path / "visible.py").write_text("VISIBLE_PATTERN\n")

        # Force ripgrep path to fail so handler uses Python fallback.
        import relace_mcp.tools.search._impl.grep_search as grep_mod

        def _raise(*_args: object, **_kwargs: object) -> object:
            raise FileNotFoundError("rg unavailable")

        monkeypatch.setattr(grep_mod.subprocess, "run", _raise)

        params = GrepSearchParams(
            query="HIDDEN_PATTERN",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "No matches" in result

        params2 = GrepSearchParams(
            query="VISIBLE_PATTERN",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result2 = grep_search_handler(params2)
        assert "visible.py" in result2


class TestGlobHandler:
    """Test glob tool handler."""

    def test_matches_basename_recursively(self, tmp_path: Path) -> None:
        """Should match basenames across subdirectories."""
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.py").write_text("b")
        (tmp_path / "sub" / "c.txt").write_text("c")

        result = glob_handler("*.py", "/repo", False, 200, str(tmp_path))
        assert "a.py" in result
        assert "sub/b.py" in result
        assert "c.txt" not in result

    def test_allows_repo_prefix_in_pattern(self, tmp_path: Path) -> None:
        """Should tolerate patterns that accidentally include /repo prefix."""
        (tmp_path / "a.py").write_text("a")

        result = glob_handler("/repo/*.py", "/repo", False, 200, str(tmp_path))
        assert "a.py" in result

    def test_matches_segment_patterns(self, tmp_path: Path) -> None:
        """Segment patterns should not match deeper paths unless using **."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("a")
        (tmp_path / "src" / "nested").mkdir()
        (tmp_path / "src" / "nested" / "b.py").write_text("b")

        result = glob_handler("src/*.py", "/repo", False, 200, str(tmp_path))
        assert "src/a.py" in result
        assert "src/nested/b.py" not in result

    def test_hidden_exclusion_and_inclusion(self, tmp_path: Path) -> None:
        """Should exclude hidden dirs by default and include when requested."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "secret.py").write_text("x")

        result = glob_handler("*.py", "/repo", False, 200, str(tmp_path))
        assert "secret.py" not in result

        result2 = glob_handler("*.py", "/repo", True, 200, str(tmp_path))
        assert ".hidden/secret.py" in result2

    def test_blocks_traversal_patterns(self, tmp_path: Path) -> None:
        """Should block ../ traversal in pattern."""
        result = glob_handler("../*.py", "/repo", False, 200, str(tmp_path))
        assert "Error" in result

    def test_respects_gitignore_file(self, tmp_path: Path) -> None:
        """Should exclude files matching .gitignore patterns."""
        (tmp_path / ".gitignore").write_text("ignored_dir/\n")
        (tmp_path / "ignored_dir").mkdir()
        (tmp_path / "ignored_dir" / "file.py").write_text("ignored")
        (tmp_path / "visible.py").write_text("visible")

        result = glob_handler("*.py", "/repo", False, 200, str(tmp_path))
        assert "visible.py" in result
        assert "ignored_dir" not in result

    def test_gitignore_prunes_directory(self, tmp_path: Path) -> None:
        """Should prune ignored directories from traversal."""
        (tmp_path / ".gitignore").write_text("big_dir/\n")
        big_dir = tmp_path / "big_dir"
        big_dir.mkdir()
        for i in range(10):
            (big_dir / f"file{i}.py").write_text(f"file{i}")
        (tmp_path / "root.py").write_text("root")

        result = glob_handler("**/*.py", "/repo", False, 200, str(tmp_path))
        assert "root.py" in result
        assert "big_dir" not in result

    def test_nested_gitignore_rules(self, tmp_path: Path) -> None:
        """Should respect nested .gitignore files."""
        (tmp_path / ".gitignore").write_text("*.log\n")
        (tmp_path / "root.log").write_text("ignored")
        (tmp_path / "root.py").write_text("visible")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.log").write_text("also ignored")
        (subdir / "nested.py").write_text("visible")

        result = glob_handler("*", "/repo", False, 200, str(tmp_path))
        assert "root.py" in result
        assert "root.log" not in result
        assert "subdir/" in result or "subdir" in result

        result2 = glob_handler("**/*.log", "/repo", False, 200, str(tmp_path))
        assert "No matches" in result2

    def test_gitignore_unignore_in_nested_gitignore(self, tmp_path: Path) -> None:
        """Nested .gitignore !patterns should override parent ignore rules."""
        (tmp_path / ".gitignore").write_text("*.log\n")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".gitignore").write_text("!keep.log\n")
        (subdir / "keep.log").write_text("keep")
        (subdir / "other.log").write_text("other")

        result = glob_handler("**/*.log", "/repo", False, 200, str(tmp_path))
        assert "subdir/keep.log" in result
        assert "other.log" not in result

    def test_glob_without_gitignore_still_works(self, tmp_path: Path) -> None:
        """Should work normally when no .gitignore exists."""
        (tmp_path / "file.py").write_text("content")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.py").write_text("nested")

        result = glob_handler("*.py", "/repo", False, 200, str(tmp_path))
        assert "file.py" in result
        assert "sub/nested.py" in result


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available on this platform")
class TestBashHandler:
    """Test bash tool handler and security."""

    def test_executes_safe_command(self, tmp_path: Path) -> None:
        """Should execute safe read-only commands."""
        (tmp_path / "test.py").write_text("print('hello')\n")

        result = bash_handler("ls -la", str(tmp_path))
        assert "test.py" in result

    def test_executes_find_command(self, tmp_path: Path) -> None:
        """Should allow find command for file discovery."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("code")

        result = bash_handler("find . -name '*.py'", str(tmp_path))
        assert "main.py" in result

    def test_executes_head_tail(self, tmp_path: Path) -> None:
        """Should allow head/tail for file inspection."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        result = bash_handler("head -n 2 test.txt", str(tmp_path))
        assert "line1" in result
        assert "line2" in result

    def test_blocks_symlink_escape(self, tmp_path: Path) -> None:
        """Should block reading paths that escape base_dir via symlink."""
        outside = tmp_path.parent / f"outside_file_{tmp_path.name}.txt"
        outside.write_text("secret\n")
        try:
            (tmp_path / "link.txt").symlink_to(outside)
        except (OSError, NotImplementedError) as e:
            pytest.skip(f"symlink is not supported in this environment: {e!r}")

        result = bash_handler("cat link.txt", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_executes_wc_command(self, tmp_path: Path) -> None:
        """Should allow wc for counting lines."""
        (tmp_path / "test.py").write_text("a\nb\nc\n")

        result = bash_handler("wc -l test.py", str(tmp_path))
        assert "3" in result

    def test_blocks_rm_command(self, tmp_path: Path) -> None:
        """Should block rm command."""
        result = bash_handler("rm file.txt", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_sudo(self, tmp_path: Path) -> None:
        """Should block sudo command."""
        result = bash_handler("sudo ls", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_curl(self, tmp_path: Path) -> None:
        """Should block curl command."""
        result = bash_handler("curl http://example.com", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_wget(self, tmp_path: Path) -> None:
        """Should block wget command."""
        result = bash_handler("wget http://example.com", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_pipe(self, tmp_path: Path) -> None:
        """Should block pipe operator."""
        result = bash_handler("ls | cat", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_redirect(self, tmp_path: Path) -> None:
        """Should block output redirection."""
        result = bash_handler("echo test > file.txt", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_command_substitution(self, tmp_path: Path) -> None:
        """Should block command substitution."""
        result = bash_handler("echo $(whoami)", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_backtick_substitution(self, tmp_path: Path) -> None:
        """Should block backtick command substitution."""
        result = bash_handler("echo `whoami`", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_blocks_shell_variable_expansion(self, tmp_path: Path) -> None:
        """Should block shell variable expansion ($...) to prevent sandbox escape."""
        result = bash_handler('echo "$HOME"', str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()

    def test_returns_no_output_message(self, tmp_path: Path) -> None:
        """Should return message for empty output."""
        result = bash_handler("true", str(tmp_path))
        assert result == "(no output)"

    def test_returns_exit_code_on_error(self, tmp_path: Path) -> None:
        """Should include exit code when command fails."""
        result = bash_handler("ls nonexistent_file_xyz", str(tmp_path))
        assert "Exit code" in result or "No such file" in result


class TestContextTruncation:
    """Test context window management."""

    def test_truncate_for_context_short_text(self) -> None:
        """Short text should not be truncated."""
        short = "Hello world"
        result = truncate_for_context(short)
        assert result == short
        assert "truncated" not in result

    def test_truncate_for_context_long_text(self) -> None:
        """Long text should be truncated with message."""
        long_text = "x" * (MAX_TOOL_RESULT_CHARS + 1000)
        result = truncate_for_context(long_text)

        assert len(result) < len(long_text)
        assert len(result) <= MAX_TOOL_RESULT_CHARS
        assert "truncated" in result
        assert str(len(long_text)) in result

    def test_estimate_context_size(self) -> None:
        """Should estimate message context size."""
        from typing import Any

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "Hello"},
            {"role": "user", "content": "World"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"arguments": '{"key": "value"}'}}],
            },
        ]

        size = estimate_context_size(messages)
        assert size == 26

    def test_estimate_context_size_counts_list_content(self) -> None:
        """Should count text in multimodal list content."""
        from typing import Any

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
                ],
            }
        ]

        assert estimate_context_size(messages) == 5


class TestGrepTruncation:
    """Test grep search truncation behavior."""

    def test_truncates_at_max_matches(self, tmp_path: Path) -> None:
        """Should truncate output at MAX_GREP_MATCHES."""
        for i in range(100):
            (tmp_path / f"file{i:03d}.py").write_text(f"MATCH_PATTERN line {i}\n")

        params = GrepSearchParams(
            query="MATCH_PATTERN",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)

        assert "capped at 50 matches" in result or "50" in result

        match_lines = [line for line in result.split("\n") if "MATCH_PATTERN" in line]
        assert len(match_lines) <= 50


class TestViewDirectoryBFS:
    """Test P2 fix: BFS-like directory listing order."""

    def test_root_files_before_subdir_contents(self, tmp_path: Path) -> None:
        """Root files should appear before subdirectory contents."""
        (tmp_path / "z_file.txt").write_text("root file")
        subdir = tmp_path / "a_subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")

        result = view_directory_handler("/repo", False, str(tmp_path))
        lines = result.strip().split("\n")

        z_idx = next(i for i, line in enumerate(lines) if "z_file.txt" in line)
        nested_idx = next(i for i, line in enumerate(lines) if "nested.txt" in line)

        assert z_idx < nested_idx

    def test_bfs_order_multiple_levels(self, tmp_path: Path) -> None:
        """BFS should list level by level."""
        (tmp_path / "root.txt").write_text("root")
        level1 = tmp_path / "level1_a"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "deep.txt").write_text("deep")

        result = view_directory_handler("/repo", False, str(tmp_path))
        lines = result.strip().split("\n")

        assert "root.txt" in lines[0]
