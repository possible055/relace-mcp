import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from relace_mcp.clients import RelaceSearchClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.search import (
    TOOL_SCHEMAS,
    FastAgenticSearchHarness,
    grep_search_handler,
    map_repo_path,
    validate_path,
    view_directory_handler,
    view_file_handler,
)


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
        result = validate_path(str(test_file), str(tmp_path))
        assert result == test_file.resolve()

    def test_blocks_path_traversal(self, tmp_path: Path) -> None:
        """Should block path traversal attempts."""
        outside_path = tmp_path.parent / "outside.py"
        with pytest.raises(RuntimeError, match="outside allowed directory"):
            validate_path(str(outside_path), str(tmp_path))

    def test_blocks_traversal_with_dots(self, tmp_path: Path) -> None:
        """Should block ../.. traversal."""
        traversal = str(tmp_path / ".." / ".." / "etc" / "passwd")
        with pytest.raises(RuntimeError, match="outside allowed directory"):
            validate_path(traversal, str(tmp_path))


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

    def test_has_four_tools(self) -> None:
        """Should have exactly 4 tools (no bash)."""
        assert len(TOOL_SCHEMAS) == 4

    def test_tool_names(self) -> None:
        """Should have correct tool names."""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert names == {"view_file", "view_directory", "grep_search", "report_back"}

    def test_no_bash_tool(self) -> None:
        """Should not include bash tool (security)."""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert "bash" not in names

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
        from relace_mcp.tools.search import truncate_for_context

        short = "Hello world"
        result = truncate_for_context(short)
        assert result == short
        assert "truncated" not in result

    def test_truncate_for_context_long_text(self) -> None:
        """Long text should be truncated with message."""
        from relace_mcp.tools.search import truncate_for_context
        from relace_mcp.tools.search.handlers import MAX_TOOL_RESULT_CHARS

        long_text = "x" * (MAX_TOOL_RESULT_CHARS + 1000)
        result = truncate_for_context(long_text)

        assert len(result) < len(long_text)
        assert "truncated" in result
        assert str(len(long_text)) in result  # Original length mentioned

    def test_estimate_context_size(self) -> None:
        """Should estimate message context size."""
        from typing import Any

        from relace_mcp.tools.search import estimate_context_size

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
