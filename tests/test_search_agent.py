import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from relace_mcp.clients import RelaceSearchClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.search import FastAgenticSearchHarness
from relace_mcp.tools.search.handlers import (
    _is_blocked_command,
    bash_handler,
    grep_search_handler,
    map_repo_path,
    view_directory_handler,
    view_file_handler,
)
from relace_mcp.tools.search.schemas import TOOL_SCHEMAS
from relace_mcp.utils import validate_file_path

DEFAULT_BASE_DIR = "/repo"


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

    def test_rejects_non_repo_path(self, tmp_path: Path) -> None:
        """Should reject paths not starting with /repo/."""
        with pytest.raises(RuntimeError, match="expects absolute paths under /repo/"):
            map_repo_path("/other/path", str(tmp_path))

    def test_rejects_relative_path(self, tmp_path: Path) -> None:
        """Should reject relative paths."""
        with pytest.raises(RuntimeError, match="expects absolute paths under /repo/"):
            map_repo_path("src/file.py", str(tmp_path))


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


class TestGrepSearchHandler:
    """Test grep_search tool handler."""

    def test_finds_pattern_in_files(self, tmp_path: Path) -> None:
        """Should find pattern matches."""
        (tmp_path / "test.py").write_text("def hello():\n    print('world')\n")

        result = grep_search_handler("hello", True, None, None, str(tmp_path))
        assert "hello" in result
        assert "test.py" in result

    def test_case_insensitive_search(self, tmp_path: Path) -> None:
        """Should support case-insensitive search."""
        (tmp_path / "test.py").write_text("HELLO world\n")

        result = grep_search_handler("hello", False, None, None, str(tmp_path))
        assert "HELLO" in result or "hello" in result.lower()

    def test_no_matches_returns_message(self, tmp_path: Path) -> None:
        """Should return 'No matches' when nothing found."""
        (tmp_path / "test.py").write_text("nothing here\n")

        result = grep_search_handler("xyz123abc", True, None, None, str(tmp_path))
        assert "No matches" in result


class TestFastAgenticSearchHarness:
    """Test the agent harness."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock(spec=RelaceSearchClient)

    def test_completes_on_report_back(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should complete when report_back is called."""
        # Setup test file
        (tmp_path / "test.py").write_text("def hello(): pass\n")

        # Mock API response with report_back tool call
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "report_back",
                                    "arguments": json.dumps(
                                        {
                                            "explanation": "Found the hello function",
                                            "files": {"test.py": [[1, 1]]},
                                        }
                                    ),
                                },
                            }
                        ]
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find hello function")

        assert result["explanation"] == "Found the hello function"
        assert "test.py" in result["files"]
        assert result["turns_used"] == 1

    def test_handles_multiple_turns(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should handle multiple turns before report_back."""
        (tmp_path / "test.py").write_text("def hello(): pass\n")

        # First call: view_file, Second call: report_back
        mock_client.chat.side_effect = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "view_file",
                                        "arguments": json.dumps(
                                            {
                                                "path": "/repo/test.py",
                                                "view_range": [1, 100],
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "function": {
                                        "name": "report_back",
                                        "arguments": json.dumps(
                                            {
                                                "explanation": "Found it",
                                                "files": {"test.py": [[1, 1]]},
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find hello")

        assert result["turns_used"] == 2
        assert mock_client.chat.call_count == 2

    def test_handles_parallel_tool_calls(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should handle multiple tool calls in single turn."""
        (tmp_path / "file1.py").write_text("content1\n")
        (tmp_path / "file2.py").write_text("content2\n")

        mock_client.chat.side_effect = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "view_file",
                                        "arguments": json.dumps(
                                            {
                                                "path": "/repo/file1.py",
                                                "view_range": [1, 100],
                                            }
                                        ),
                                    },
                                },
                                {
                                    "id": "call_2",
                                    "function": {
                                        "name": "view_file",
                                        "arguments": json.dumps(
                                            {
                                                "path": "/repo/file2.py",
                                                "view_range": [1, 100],
                                            }
                                        ),
                                    },
                                },
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_3",
                                    "function": {
                                        "name": "report_back",
                                        "arguments": json.dumps(
                                            {
                                                "explanation": "Found both files",
                                                "files": {
                                                    "file1.py": [[1, 1]],
                                                    "file2.py": [[1, 1]],
                                                },
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find files")

        assert len(result["files"]) == 2

    def test_raises_on_max_turns_exceeded(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should raise error when max turns exceeded."""
        # Always return view_file, never report_back
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "view_directory",
                                    "arguments": json.dumps(
                                        {
                                            "path": "/repo",
                                            "include_hidden": False,
                                        }
                                    ),
                                },
                            }
                        ]
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)

        with pytest.raises(RuntimeError, match="did not complete"):
            harness.run("This will timeout")


class TestToolSchemas:
    """Test tool schema definitions."""

    def test_has_five_tools(self) -> None:
        """Should have exactly 5 tools (including bash)."""
        assert len(TOOL_SCHEMAS) == 5

    def test_tool_names(self) -> None:
        """Should have correct tool names."""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert names == {"view_file", "view_directory", "grep_search", "report_back", "bash"}

    def test_bash_tool_exists(self) -> None:
        """Should include bash tool for code exploration."""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert "bash" in names

    def test_schema_has_default_per_official_docs(self) -> None:
        """Per Relace official docs, certain params should have default values."""
        # view_file.view_range should have default [1, 100]
        view_file = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "view_file")
        view_range = view_file["function"]["parameters"]["properties"]["view_range"]
        assert view_range.get("default") == [1, 100]

        # view_directory.include_hidden should have default False
        view_dir = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "view_directory")
        include_hidden = view_dir["function"]["parameters"]["properties"]["include_hidden"]
        assert include_hidden.get("default") is False

        # grep_search.case_sensitive should have default True
        grep = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "grep_search")
        case_sensitive = grep["function"]["parameters"]["properties"]["case_sensitive"]
        assert case_sensitive.get("default") is True


class TestParallelToolCallsFix:
    """Test P0 fix: parallel tool calls with report_back not last."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock(spec=RelaceSearchClient)

    def test_report_back_not_last_still_processes_all(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """report_back in middle should still process all tool calls."""
        (tmp_path / "file1.py").write_text("content1\n")
        (tmp_path / "file2.py").write_text("content2\n")

        # report_back is call_2, but there's call_3 after it
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "view_file",
                                    "arguments": json.dumps(
                                        {
                                            "path": "/repo/file1.py",
                                            "view_range": [1, 100],
                                        }
                                    ),
                                },
                            },
                            {
                                "id": "call_2",
                                "function": {
                                    "name": "report_back",
                                    "arguments": json.dumps(
                                        {
                                            "explanation": "Found files",
                                            "files": {"file1.py": [[1, 1]]},
                                        }
                                    ),
                                },
                            },
                            {
                                "id": "call_3",
                                "function": {
                                    "name": "view_file",
                                    "arguments": json.dumps(
                                        {
                                            "path": "/repo/file2.py",
                                            "view_range": [1, 100],
                                        }
                                    ),
                                },
                            },
                        ]
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find files")

        # Should complete with report_back result
        assert result["explanation"] == "Found files"
        # Only 1 API call needed
        assert mock_client.chat.call_count == 1

    def test_malformed_json_arguments_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Malformed JSON in arguments should return error, not crash."""
        mock_client.chat.side_effect = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "view_file",
                                        "arguments": "{invalid json",  # Malformed!
                                    },
                                },
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "function": {
                                        "name": "report_back",
                                        "arguments": json.dumps(
                                            {
                                                "explanation": "Done",
                                                "files": {},
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Test malformed")

        # Should complete without crash
        assert result["explanation"] == "Done"
        assert mock_client.chat.call_count == 2

    def test_non_dict_arguments_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Valid JSON but non-dict arguments should return error, not crash."""
        mock_client.chat.side_effect = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "report_back",
                                        # Valid JSON but string, not dict
                                        "arguments": '"oops"',
                                    },
                                },
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "function": {
                                        "name": "report_back",
                                        "arguments": json.dumps(
                                            {
                                                "explanation": "Recovered",
                                                "files": {},
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Test non-dict args")

        # Should complete without crash, recovered in turn 2
        assert result["explanation"] == "Recovered"
        assert mock_client.chat.call_count == 2


class TestViewDirectoryBFS:
    """Test P2 fix: BFS-like directory listing order."""

    def test_root_files_before_subdir_contents(self, tmp_path: Path) -> None:
        """Root files should appear before subdirectory contents."""
        # Create structure:
        # root/
        #   z_file.txt  (should appear early despite name)
        #   a_subdir/
        #     nested.txt
        (tmp_path / "z_file.txt").write_text("root file")
        subdir = tmp_path / "a_subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")

        result = view_directory_handler("/repo", False, str(tmp_path))
        lines = result.strip().split("\n")

        # z_file.txt should be in root level items (before a_subdir contents)
        z_idx = next(i for i, line in enumerate(lines) if "z_file.txt" in line)
        nested_idx = next(i for i, line in enumerate(lines) if "nested.txt" in line)

        # Root file should appear before nested file
        assert z_idx < nested_idx

    def test_bfs_order_multiple_levels(self, tmp_path: Path) -> None:
        """BFS should list level by level."""
        # Create structure:
        # root/
        #   level1_a/
        #     level2/
        #       deep.txt
        #   root.txt
        (tmp_path / "root.txt").write_text("root")
        level1 = tmp_path / "level1_a"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "deep.txt").write_text("deep")

        result = view_directory_handler("/repo", False, str(tmp_path))
        lines = result.strip().split("\n")

        # Order should be: root.txt, level1_a/, level2/, deep.txt
        assert "root.txt" in lines[0]


class TestGrepTruncation:
    """Test grep search truncation behavior."""

    def test_truncates_at_max_matches(self, tmp_path: Path) -> None:
        """Should truncate output at MAX_GREP_MATCHES."""
        # Create many files with matches
        for i in range(100):
            (tmp_path / f"file{i:03d}.py").write_text(f"MATCH_PATTERN line {i}\n")

        result = grep_search_handler("MATCH_PATTERN", True, None, None, str(tmp_path))

        # Should have truncation message
        assert "capped at 50 matches" in result or "50" in result

        # Count actual match lines (excluding truncation message)
        match_lines = [line for line in result.split("\n") if "MATCH_PATTERN" in line]
        assert len(match_lines) <= 50


class TestContextTruncation:
    """Test context window management."""

    def test_truncate_for_context_short_text(self) -> None:
        """Short text should not be truncated."""
        from relace_mcp.tools.search.handlers import truncate_for_context

        short = "Hello world"
        result = truncate_for_context(short)
        assert result == short
        assert "truncated" not in result

    def test_truncate_for_context_long_text(self) -> None:
        """Long text should be truncated with message."""
        from relace_mcp.tools.search.handlers import MAX_TOOL_RESULT_CHARS, truncate_for_context

        long_text = "x" * (MAX_TOOL_RESULT_CHARS + 1000)
        result = truncate_for_context(long_text)

        assert len(result) < len(long_text)
        assert "truncated" in result
        assert str(len(long_text)) in result  # Original length mentioned

    def test_estimate_context_size(self) -> None:
        """Should estimate message context size."""
        from typing import Any

        from relace_mcp.tools.search.handlers import estimate_context_size

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "Hello"},
            {"role": "user", "content": "World"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"arguments": '{"key": "value"}'}}],
            },
        ]

        size = estimate_context_size(messages)
        # "Hello" + "World" + '{"key": "value"}' = 5 + 5 + 16 = 26
        assert size == 26


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

    def test_returns_no_output_message(self, tmp_path: Path) -> None:
        """Should return message for empty output."""
        result = bash_handler("true", str(tmp_path))
        assert result == "(no output)"

    def test_returns_exit_code_on_error(self, tmp_path: Path) -> None:
        """Should include exit code when command fails."""
        result = bash_handler("ls nonexistent_file_xyz", str(tmp_path))
        assert "Exit code" in result or "No such file" in result


class TestIsBlockedCommand:
    """Test command blocking logic."""

    def test_blocks_rm(self) -> None:
        blocked, _ = _is_blocked_command("rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_rm_rf(self) -> None:
        blocked, _ = _is_blocked_command("rm -rf /", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_full_path_rm(self) -> None:
        blocked, _ = _is_blocked_command("/bin/rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_ls(self) -> None:
        blocked, _ = _is_blocked_command("ls -la", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_cat(self) -> None:
        blocked, _ = _is_blocked_command("cat file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_grep(self) -> None:
        blocked, _ = _is_blocked_command("grep pattern file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_find(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.py'", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_log(self) -> None:
        blocked, _ = _is_blocked_command("git log -n 10", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_pipe(self) -> None:
        blocked, _ = _is_blocked_command("cat file | grep pattern", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_redirect_to_file(self) -> None:
        blocked, _ = _is_blocked_command("echo test > output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_append_redirect(self) -> None:
        blocked, _ = _is_blocked_command("echo test >> output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_empty_command(self) -> None:
        blocked, _ = _is_blocked_command("", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_semicolon_rm(self) -> None:
        blocked, _ = _is_blocked_command("ls; rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_and_rm(self) -> None:
        blocked, _ = _is_blocked_command("ls && rm file.txt", DEFAULT_BASE_DIR)
        assert blocked


class TestAbsolutePathBlocking:
    """Test absolute path sandbox enforcement."""

    def test_blocks_cat_etc_passwd(self) -> None:
        """Should block reading /etc/passwd."""
        blocked, reason = _is_blocked_command("cat /etc/passwd", DEFAULT_BASE_DIR)
        assert blocked
        assert "/etc/passwd" in reason or "Absolute path" in reason

    def test_blocks_cat_etc_shadow(self) -> None:
        """Should block reading /etc/shadow."""
        blocked, reason = _is_blocked_command("cat /etc/shadow", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_root(self) -> None:
        """Should block find starting from root."""
        blocked, reason = _is_blocked_command("find / -name '*.py'", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_ls_home(self) -> None:
        """Should block listing home directory."""
        blocked, reason = _is_blocked_command("ls /home", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_head_var_log(self) -> None:
        """Should block reading system logs."""
        blocked, reason = _is_blocked_command("head /var/log/syslog", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_repo_path(self) -> None:
        """Should allow /repo paths."""
        blocked, _ = _is_blocked_command("cat /repo/file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_repo_subpath(self) -> None:
        """Should allow /repo/subdir paths."""
        blocked, _ = _is_blocked_command("ls /repo/src/", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_relative_path(self) -> None:
        """Should allow relative paths."""
        blocked, _ = _is_blocked_command("cat ./file.txt", DEFAULT_BASE_DIR)
        assert not blocked


class TestWriteOperationBlocking:
    """Test blocking of write/modify operations."""

    def test_blocks_touch(self) -> None:
        """Should block touch command."""
        blocked, _ = _is_blocked_command("touch newfile.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_tee(self) -> None:
        """Should block tee command."""
        blocked, _ = _is_blocked_command("tee output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_sed_inplace(self) -> None:
        """Should block sed -i (in-place edit)."""
        blocked, _ = _is_blocked_command("sed -i 's/old/new/g' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_mkdir(self) -> None:
        """Should block mkdir command."""
        blocked, _ = _is_blocked_command("mkdir newdir", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_ln(self) -> None:
        """Should block ln (symlink creation)."""
        blocked, _ = _is_blocked_command("ln -s target link", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_exec(self) -> None:
        """Should block find -exec."""
        blocked, _ = _is_blocked_command("find . -name '*.py' -exec rm {} \\;", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_delete(self) -> None:
        """Should block find -delete."""
        blocked, _ = _is_blocked_command("find . -name '*.pyc' -delete", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_xargs_rm(self) -> None:
        """Should block xargs with rm."""
        blocked, _ = _is_blocked_command("find . -name '*.tmp' | xargs rm", DEFAULT_BASE_DIR)
        assert blocked


class TestGitSecurityBlocking:
    """Test git subcommand security."""

    def test_allows_git_log(self) -> None:
        """Should allow git log."""
        blocked, _ = _is_blocked_command("git log -n 10", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_show(self) -> None:
        """Should allow git show."""
        blocked, _ = _is_blocked_command("git show HEAD", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_diff(self) -> None:
        """Should allow git diff."""
        blocked, _ = _is_blocked_command("git diff HEAD~1", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_status(self) -> None:
        """Should allow git status."""
        blocked, _ = _is_blocked_command("git status", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_blame(self) -> None:
        """Should allow git blame."""
        blocked, _ = _is_blocked_command("git blame file.py", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_git_clone(self) -> None:
        """Should block git clone (network operation)."""
        blocked, _ = _is_blocked_command("git clone https://github.com/user/repo", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_fetch(self) -> None:
        """Should block git fetch (network operation)."""
        blocked, _ = _is_blocked_command("git fetch origin", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_pull(self) -> None:
        """Should block git pull (network operation)."""
        blocked, _ = _is_blocked_command("git pull origin main", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_push(self) -> None:
        """Should block git push (network operation)."""
        blocked, _ = _is_blocked_command("git push origin main", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_checkout(self) -> None:
        """Should block git checkout (modifies working tree)."""
        blocked, _ = _is_blocked_command("git checkout -- .", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_reset(self) -> None:
        """Should block git reset (modifies repo state)."""
        blocked, _ = _is_blocked_command("git reset --hard HEAD", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_clean(self) -> None:
        """Should block git clean (deletes files)."""
        blocked, _ = _is_blocked_command("git clean -fd", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_commit(self) -> None:
        """Should block git commit (modifies repo)."""
        blocked, _ = _is_blocked_command("git commit -m 'msg'", DEFAULT_BASE_DIR)
        assert blocked


class TestPythonSecurityBlocking:
    """Test Python command security."""

    def test_blocks_python_file_write(self) -> None:
        """Should block Python file write operations."""
        blocked, _ = _is_blocked_command("python -c \"open('f','w').write('x')\"", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_pathlib(self) -> None:
        """Should block Python pathlib usage."""
        blocked, _ = _is_blocked_command(
            "python3 -c \"import pathlib; print(pathlib.Path('x').read_text())\"",
            DEFAULT_BASE_DIR,
        )
        assert blocked

    def test_blocks_http_client(self) -> None:
        """Should block Python http.client usage."""
        blocked, _ = _is_blocked_command('python3 -c "import http.client"', DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python_requests(self) -> None:
        """Should block Python requests (network)."""
        blocked, _ = _is_blocked_command(
            "python -c \"import requests; requests.get('http://x')\"",
            DEFAULT_BASE_DIR,
        )
        assert blocked

    def test_blocks_python_urllib(self) -> None:
        """Should block Python urllib (network)."""
        blocked, _ = _is_blocked_command('python -c "import urllib.request"', DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python_subprocess(self) -> None:
        """Should block Python subprocess."""
        blocked, _ = _is_blocked_command('python -c "import subprocess"', DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python_os_system(self) -> None:
        """Should block Python os.system."""
        blocked, _ = _is_blocked_command(
            "python -c \"import os; os.system('rm -rf /')\"",
            DEFAULT_BASE_DIR,
        )
        assert blocked

    def test_blocks_python_script_execution(self) -> None:
        """Should block Python script file execution."""
        blocked, _ = _is_blocked_command("python script.py", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python3_script_execution(self) -> None:
        """Should block Python3 script file execution."""
        blocked, _ = _is_blocked_command("python3 script.py", DEFAULT_BASE_DIR)
        assert blocked


class TestPipeAllowedInQuotes:
    """Test that pipe is blocked everywhere for maximum safety (KISS)."""

    def test_blocks_grep_e_with_pipe_pattern(self) -> None:
        """Should block grep -E 'foo|bar' pattern due to strict pipe blocking."""
        blocked, _ = _is_blocked_command("grep -E 'foo|bar' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_egrep_with_pipe_pattern(self) -> None:
        """Should block egrep 'foo|bar' pattern."""
        blocked, _ = _is_blocked_command("egrep 'foo|bar' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_actual_pipe_operator(self) -> None:
        """Should still block actual pipe operator with spaces."""
        blocked, _ = _is_blocked_command("cat file | grep pattern", DEFAULT_BASE_DIR)
        assert blocked


class TestCommandNotInAllowlist:
    """Test that unknown commands are blocked."""

    def test_blocks_unknown_command(self) -> None:
        """Should block commands not in allowlist."""
        blocked, reason = _is_blocked_command("someunknowncommand arg", DEFAULT_BASE_DIR)
        assert blocked
        assert "allowlist" in reason.lower()

    def test_blocks_make(self) -> None:
        """Should block make (build tool)."""
        blocked, _ = _is_blocked_command("make all", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_npm(self) -> None:
        """Should block npm."""
        blocked, _ = _is_blocked_command("npm install", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_pip(self) -> None:
        """Should block pip."""
        blocked, _ = _is_blocked_command("pip install requests", DEFAULT_BASE_DIR)
        assert blocked
