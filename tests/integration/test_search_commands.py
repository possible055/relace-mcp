import shutil
from pathlib import Path

import pytest

from relace_mcp.tools.search._impl import (
    bash_handler,
    glob_handler,
    grep_search_handler,
    view_file_handler,
)
from relace_mcp.tools.search.schemas.types import GrepSearchParams


class TestGrepSearchIntegration:
    def test_basic_pattern_matching(self, tmp_path: Path) -> None:
        (tmp_path / "hello.py").write_text("def hello():\n    return 'world'\n")
        (tmp_path / "goodbye.py").write_text("def goodbye():\n    return 'bye'\n")

        params = GrepSearchParams(
            query="hello",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "hello" in result
        assert "hello.py" in result

    def test_case_insensitive_search(self, tmp_path: Path) -> None:
        (tmp_path / "mixed.py").write_text("Hello World\nhello world\nHELLO WORLD\n")

        params = GrepSearchParams(
            query="hello",
            case_sensitive=False,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "Hello" in result or "hello" in result or "HELLO" in result
        lines_with_match = [line for line in result.splitlines() if "ello" in line.lower()]
        assert len(lines_with_match) >= 3

    def test_include_pattern_filter(self, tmp_path: Path) -> None:
        (tmp_path / "target.py").write_text("FINDME here\n")
        (tmp_path / "other.txt").write_text("FINDME there\n")

        params = GrepSearchParams(
            query="FINDME",
            case_sensitive=True,
            include_pattern="*.py",
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert "target.py" in result
        assert "other.txt" not in result

    def test_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "empty.py").write_text("nothing interesting\n")

        params = GrepSearchParams(
            query="NONEXISTENT_TOKEN_XYZ",
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
            base_dir=str(tmp_path),
        )
        result = grep_search_handler(params)
        assert result == "No matches found."


class TestGlobIntegration:
    def test_glob_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("code")
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "util.py").write_text("code")
        (tmp_path / "readme.md").write_text("docs")

        result = glob_handler("**/*.py", ".", False, 100, str(tmp_path))
        assert "main.py" in result
        assert "util.py" in result
        assert "readme.md" not in result

    def test_specific_filename_pattern(self, tmp_path: Path) -> None:
        (tmp_path / "config.json").write_text("{}")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "script.py").write_text("")

        result = glob_handler("*.json", ".", False, 100, str(tmp_path))
        assert "config.json" in result
        assert "data.json" in result
        assert "script.py" not in result

    def test_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("content")

        result = glob_handler("*.xyz", ".", False, 100, str(tmp_path))
        assert result == "No matches found."

    def test_directory_pattern_with_trailing_slash(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "file.txt").write_text("")

        result = glob_handler("*/", ".", False, 100, str(tmp_path))
        assert "src/" in result
        assert "tests/" in result
        assert "file.txt" not in result


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
class TestBashIntegration:
    def test_echo_hello(self, tmp_path: Path) -> None:
        result = bash_handler("echo hello", str(tmp_path))
        assert "hello" in result

    def test_ls_shows_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.py").write_text("bbb")

        result = bash_handler("ls", str(tmp_path))
        assert "a.txt" in result
        assert "b.py" in result

    def test_blocked_command(self, tmp_path: Path) -> None:
        result = bash_handler("rm -rf /", str(tmp_path))
        assert "Error" in result
        assert "blocked" in result.lower()


class TestViewFileIntegration:
    def test_view_range(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(1, 21))
        target = tmp_path / "data.txt"
        target.write_text(content)

        result = view_file_handler(str(target), [1, 5], str(tmp_path))
        assert "1 line 1" in result
        assert "5 line 5" in result
        assert "6 line 6" not in result

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = view_file_handler(str(tmp_path / "nope.txt"), [1, 10], str(tmp_path))
        assert "Error" in result
        assert "not found" in result.lower()

    def test_view_range_to_end(self, tmp_path: Path) -> None:
        target = tmp_path / "small.txt"
        target.write_text("alpha\nbeta\ngamma\n")

        result = view_file_handler(str(target), [2, -1], str(tmp_path))
        assert "2 beta" in result
        assert "3 gamma" in result
        assert "truncated" not in result
