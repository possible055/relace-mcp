import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.search import FastAgenticSearchHarness
from relace_mcp.tools.search.schemas import TOOL_SCHEMAS


def _make_view_file_call(call_id: str, path: str) -> dict:
    """Build view_file tool call for tests."""
    return {
        "id": call_id,
        "function": {
            "name": "view_file",
            "arguments": json.dumps({"path": path, "view_range": [1, 100]}),
        },
    }


def _make_report_back_call(call_id: str, explanation: str, files: dict) -> dict:
    """Build report_back tool call for tests."""
    return {
        "id": call_id,
        "function": {
            "name": "report_back",
            "arguments": json.dumps({"explanation": explanation, "files": files}),
        },
    }


class TestFastAgenticSearchHarness:
    """Test the agent harness."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock(spec=SearchLLMClient)

    def test_completes_on_report_back(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should complete when report_back is called."""
        (tmp_path / "test.py").write_text("def hello(): pass\n")

        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            _make_report_back_call(
                                "call_1",
                                "Found the hello function",
                                {"test.py": [[1, 1]]},
                            )
                        ]
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find hello function")

        assert result["explanation"] == "Found the hello function"
        # Files are now normalized to absolute paths
        expected_path = str(tmp_path / "test.py")
        assert expected_path in result["files"]
        assert result["turns_used"] == 1

    def test_report_back_ignores_invalid_ranges_type(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Invalid range payloads should be ignored (no TypeError)."""
        (tmp_path / "test.py").write_text("def hello(): pass\n")

        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            _make_report_back_call(
                                "call_1",
                                "Bad ranges should not crash",
                                {"test.py": "oops"},
                            )
                        ]
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find hello function")

        assert result["explanation"] == "Bad ranges should not crash"
        assert result["files"] == {}

    def test_handles_multiple_turns(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should handle multiple turns before report_back."""
        (tmp_path / "test.py").write_text("def hello(): pass\n")

        mock_client.chat.side_effect = [
            {
                "choices": [
                    {"message": {"tool_calls": [_make_view_file_call("call_1", "/repo/test.py")]}}
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                _make_report_back_call("call_2", "Found it", {"test.py": [[1, 1]]})
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
                                _make_view_file_call("call_1", "/repo/file1.py"),
                                _make_view_file_call("call_2", "/repo/file2.py"),
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
                                _make_report_back_call(
                                    "call_3",
                                    "Found both files",
                                    {"file1.py": [[1, 1]], "file2.py": [[1, 1]]},
                                )
                            ]
                        }
                    }
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find files")

        assert len(result["files"]) == 2

    def test_returns_partial_on_max_turns_exceeded(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return partial results (not raise) when max turns exceeded."""
        (tmp_path / "test.py").write_text("def hello(): pass\n")

        # Always request a tool (never report_back) so the harness hits SEARCH_MAX_TURNS.
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [_make_view_file_call("call_1", "/repo/test.py")],
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("This will timeout")

        assert result["partial"] is True
        assert result["turns_used"] > 0
        assert "did not complete" in result["explanation"]
        # Files are now keyed by absolute path
        expected_path = str(tmp_path / "test.py")
        assert expected_path in result["files"]

    def test_partial_results_normalize_view_file_ranges(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Partial results should never contain invalid ranges like end=-1."""
        import relace_mcp.tools.search.harness as harness_mod

        monkeypatch.setattr(harness_mod, "SEARCH_MAX_TURNS", 2)
        (tmp_path / "test.py").write_text("line1\nline2\nline3\n")

        view_to_eof_call = {
            "id": "call_1",
            "function": {
                "name": "view_file",
                "arguments": json.dumps({"path": "/repo/test.py", "view_range": [1, -1]}),
            },
        }

        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [view_to_eof_call],
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("This will timeout")

        # Files are now keyed by absolute path
        expected_path = str(tmp_path / "test.py")
        ranges = result["files"][expected_path]
        assert ranges
        assert all(r[0] > 0 and r[1] >= r[0] for r in ranges)
        assert all(r[1] != -1 for r in ranges)


class TestParallelToolCallsFix:
    """Test P0 fix: parallel tool calls with report_back not last."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock(spec=SearchLLMClient)

    def test_report_back_not_last_still_processes_all(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """report_back in middle should still process all tool calls."""
        (tmp_path / "file1.py").write_text("content1\n")
        (tmp_path / "file2.py").write_text("content2\n")

        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            _make_view_file_call("call_1", "/repo/file1.py"),
                            _make_report_back_call("call_2", "Found files", {"file1.py": [[1, 1]]}),
                            _make_view_file_call("call_3", "/repo/file2.py"),
                        ]
                    }
                }
            ]
        }

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Find files")

        assert result["explanation"] == "Found files"
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
                                        "arguments": "{invalid json",
                                    },
                                },
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {"message": {"tool_calls": [_make_report_back_call("call_2", "Done", {})]}}
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Test malformed")

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
                    {"message": {"tool_calls": [_make_report_back_call("call_2", "Recovered", {})]}}
                ]
            },
        ]

        harness = FastAgenticSearchHarness(mock_config, mock_client)
        result = harness.run("Test non-dict args")

        assert result["explanation"] == "Recovered"
        assert mock_client.chat.call_count == 2


class TestToolSchemas:
    """Test tool schema definitions."""

    def test_has_five_default_tools(self) -> None:
        """Should have exactly 5 tools by default (bash is opt-in)."""
        assert len(TOOL_SCHEMAS) == 5

    def test_tool_names(self) -> None:
        """Should have correct default tool names (no bash)."""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert names == {
            "view_file",
            "view_directory",
            "grep_search",
            "glob",
            "report_back",
        }

    def test_bash_tool_opt_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """bash should be available when explicitly enabled."""
        import shutil

        from relace_mcp.tools.search.schemas import get_tool_schemas

        monkeypatch.setenv(
            "RELACE_SEARCH_ENABLED_TOOLS", "view_file,view_directory,grep_search,glob,bash"
        )
        schemas = get_tool_schemas()
        names = {t["function"]["name"] for t in schemas}
        if shutil.which("bash") is None:
            pytest.skip("bash is not available on this platform")
        assert "bash" in names

    def test_glob_tool_exists(self) -> None:
        """Should include glob tool for file discovery."""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert "glob" in names

    def test_get_tool_schemas_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Allowlist should restrict tools but always keep report_back."""
        from relace_mcp.tools.search.schemas import get_tool_schemas

        monkeypatch.setenv("RELACE_SEARCH_ENABLED_TOOLS", "view_file,grep_search,glob")

        schemas = get_tool_schemas()
        names = {t["function"]["name"] for t in schemas}
        assert names == {"view_file", "grep_search", "glob", "report_back"}

    def test_schema_has_default_per_official_docs(self) -> None:
        """Per Relace official docs, certain params should have default values."""
        view_file = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "view_file")
        view_range = view_file["function"]["parameters"]["properties"]["view_range"]
        assert view_range.get("default") == [1, 100]

        view_dir = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "view_directory")
        include_hidden = view_dir["function"]["parameters"]["properties"]["include_hidden"]
        assert include_hidden.get("default") is False

        grep = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "grep_search")
        case_sensitive = grep["function"]["parameters"]["properties"]["case_sensitive"]
        assert case_sensitive.get("default") is True
