import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.search.harness import ChannelEvidence, DualChannelHarness
from relace_mcp.tools.search.harness.channels import LexicalChannel, SemanticChannel
from relace_mcp.tools.search.harness.merger import MergerAgent


def _make_tool_call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "function": {"name": name, "arguments": json.dumps(args)},
    }


class TestChannelEvidence:
    """Test ChannelEvidence dataclass."""

    def test_default_values(self) -> None:
        evidence = ChannelEvidence(files={})
        assert evidence.files == {}
        assert evidence.observations == []
        assert evidence.turns_used == 0
        assert evidence.partial is False
        assert evidence.error is None

    def test_with_data(self) -> None:
        evidence = ChannelEvidence(
            files={"/repo/test.py": [[1, 10], [20, 30]]},
            observations=["Found function"],
            turns_used=3,
            partial=True,
            error="timeout",
        )
        assert len(evidence.files) == 1
        assert evidence.turns_used == 3
        assert evidence.error == "timeout"


class TestLexicalChannel:
    """Test LexicalChannel tool isolation."""

    def test_allowed_tools(self) -> None:
        assert LexicalChannel.ALLOWED_TOOLS == frozenset(
            {"view_file", "view_directory", "grep_search", "glob"}
        )

    def test_no_lsp_tools(self) -> None:
        lsp_tools = {"find_symbol", "search_symbol", "list_symbols", "call_graph", "get_type"}
        assert LexicalChannel.ALLOWED_TOOLS.isdisjoint(lsp_tools)


class TestSemanticChannel:
    """Test SemanticChannel tool isolation."""

    def test_allowed_tools(self) -> None:
        assert SemanticChannel.ALLOWED_TOOLS == frozenset(
            {"view_file", "search_symbol", "find_symbol", "list_symbols", "call_graph", "get_type"}
        )

    def test_no_grep(self) -> None:
        assert "grep_search" not in SemanticChannel.ALLOWED_TOOLS
        assert "glob" not in SemanticChannel.ALLOWED_TOOLS
        assert "view_directory" not in SemanticChannel.ALLOWED_TOOLS


class TestMergerAgent:
    """Test MergerAgent merge logic."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock(spec=SearchLLMClient)

    def test_fallback_merge_unions_files(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        merger = MergerAgent(mock_config, mock_client, mock_config.base_dir)
        lexical = ChannelEvidence(
            files={"/repo/a.py": [[1, 10]]},
            turns_used=3,
        )
        semantic = ChannelEvidence(
            files={"/repo/b.py": [[20, 30]]},
            turns_used=3,
        )

        result = merger._fallback_merge("test query", lexical, semantic)

        # Paths will be normalized to absolute paths
        normalized_files = result["files"]
        assert len(normalized_files) == 2
        assert result["partial"] is True
        assert "[FALLBACK]" in result["explanation"]

    def test_fallback_merge_combines_overlapping_ranges(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        merger = MergerAgent(mock_config, mock_client, mock_config.base_dir)
        lexical = ChannelEvidence(files={"/repo/a.py": [[1, 10], [15, 20]]}, turns_used=3)
        semantic = ChannelEvidence(files={"/repo/a.py": [[8, 18]]}, turns_used=3)

        result = merger._fallback_merge("test", lexical, semantic)

        # After merge, expect single combined range
        assert len(result["files"]) == 1
        ranges = list(result["files"].values())[0]
        assert ranges == [[1, 20]]

    def test_merge_parses_tool_call(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            _make_tool_call(
                                "call_1",
                                "merge_report",
                                {
                                    "explanation": "Merged results",
                                    "files": {"/repo/test.py": [[1, 50]]},
                                },
                            )
                        ]
                    }
                }
            ]
        }

        merger = MergerAgent(mock_config, mock_client, mock_config.base_dir)
        lexical = ChannelEvidence(files={}, turns_used=3)
        semantic = ChannelEvidence(files={}, turns_used=3)

        result = merger.merge("query", lexical, semantic)

        assert result["explanation"] == "Merged results"
        # Path will be normalized
        assert len(result["files"]) == 1
        assert result["turns_used"] == 4


class TestDualChannelHarness:
    """Test DualChannelHarness orchestration."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock(spec=SearchLLMClient)

    def test_fallback_to_single_harness_without_lsp(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        harness = DualChannelHarness(mock_config, mock_client, lsp_languages=frozenset())
        assert harness._dual_mode is False

    def test_dual_mode_enabled_with_lsp(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        harness = DualChannelHarness(mock_config, mock_client, lsp_languages=frozenset({"python"}))
        assert harness._dual_mode is True

    def test_handle_exception_converts_to_evidence(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        harness = DualChannelHarness(mock_config, mock_client, lsp_languages=frozenset({"python"}))

        exc = RuntimeError("Test error")
        result = harness._handle_exception(exc, "lexical")

        assert isinstance(result, ChannelEvidence)
        assert result.error == "Test error"
        assert result.partial is True

    def test_handle_exception_passes_through_evidence(
        self, mock_config: RelaceConfig, mock_client: MagicMock
    ) -> None:
        harness = DualChannelHarness(mock_config, mock_client, lsp_languages=frozenset({"python"}))

        evidence = ChannelEvidence(files={"/repo/a.py": [[1, 10]]}, turns_used=3)
        result = harness._handle_exception(evidence, "lexical")

        assert result is evidence
