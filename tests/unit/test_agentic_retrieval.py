from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import RelaceRepoClient, SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.repo.retrieval import (
    agentic_retrieval_logic,
    build_semantic_hints_section,
)


class TestBuildSemanticHintsSection:
    def test_formats_results_correctly(self) -> None:
        results = [
            {"filename": "src/auth.py", "score": 0.85},
            {"filename": "src/login.py", "score": 0.72},
        ]
        section = build_semantic_hints_section(results)

        assert "<semantic_hints>" in section
        assert "src/auth.py (score: 0.85)" in section
        assert "src/login.py (score: 0.72)" in section
        assert "</semantic_hints>" in section

    def test_empty_results_returns_empty(self) -> None:
        section = build_semantic_hints_section([])
        assert section == ""

    def test_respects_max_hints(self) -> None:
        results = [{"filename": f"file{i}.py", "score": 0.9 - i * 0.1} for i in range(10)]
        section = build_semantic_hints_section(results, max_hints=3)

        assert "file0.py" in section
        assert "file1.py" in section
        assert "file2.py" in section
        assert "file3.py" not in section

    def test_handles_file_key_fallback(self) -> None:
        results = [{"file": "src/utils.py", "score": 0.65}]
        section = build_semantic_hints_section(results)

        assert "src/utils.py (score: 0.65)" in section


class TestAgenticRetrievalLogic:
    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_repo_client(self) -> MagicMock:
        return MagicMock(spec=RelaceRepoClient)

    @pytest.fixture
    def mock_search_client(self) -> MagicMock:
        client = MagicMock(spec=SearchLLMClient)
        client.api_compat = "relace"
        return client

    @pytest.mark.asyncio
    async def test_fallback_on_cloud_error(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_cloud.return_value = {"error": "Network error", "results": []}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Found files", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "find auth logic",
            )

            assert "warnings" in result
            assert any("Cloud search failed" in w for w in result["warnings"])
            assert result["cloud_hints_used"] == 0

    @pytest.mark.asyncio
    async def test_fallback_on_empty_cloud_results(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_cloud.return_value = {"results": []}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Found files", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "find something",
            )

            assert "warnings" in result
            assert any("no results" in w for w in result["warnings"])
            assert result["cloud_hints_used"] == 0

    @pytest.mark.asyncio
    async def test_hints_injected_in_prompt(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_cloud.return_value = {
                "results": [
                    {"filename": "src/auth.py", "score": 0.85},
                    {"filename": "src/login.py", "score": 0.72},
                ]
            }
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Found auth", "files": {}, "turns_used": 2}
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "find authentication",
            )

            # Verify harness was called with user_prompt_override containing hints
            mock_harness_cls.assert_called_once()
            call_kwargs = mock_harness_cls.call_args.kwargs
            assert "user_prompt_override" in call_kwargs
            prompt = call_kwargs["user_prompt_override"]
            assert "<semantic_hints>" in prompt
            assert "src/auth.py" in prompt

            assert result["cloud_hints_used"] == 2

    @pytest.mark.asyncio
    async def test_happy_path(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_cloud.return_value = {"results": [{"filename": "src/core.py", "score": 0.9}]}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={
                    "explanation": "Result",
                    "files": {"src/core.py": [[1, 10]]},
                    "turns_used": 1,
                }
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            assert result["explanation"] == "Result"
            assert "src/core.py" in result["files"]
            assert result["cloud_hints_used"] == 1
            assert "trace_id" in result

    @pytest.mark.asyncio
    async def test_cloud_search_exception_handling(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_cloud.side_effect = Exception("Fatal cloud error")
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Fallback works", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            assert "warnings" in result
            assert any("Cloud search error: Fatal cloud error" in w for w in result["warnings"])
            assert result["cloud_hints_used"] == 0


class TestAutoSync:
    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_repo_client(self) -> MagicMock:
        return MagicMock(spec=RelaceRepoClient)

    @pytest.fixture
    def mock_search_client(self) -> MagicMock:
        client = MagicMock(spec=SearchLLMClient)
        client.api_compat = "relace"
        return client

    @pytest.mark.asyncio
    async def test_auto_sync_triggered_when_needs_sync(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.AGENTIC_AUTO_SYNC", True),
            patch("relace_mcp.tools.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.tools.repo.retrieval.cloud_sync_logic") as mock_sync,
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_info.return_value = {"status": {"needs_sync": True}}
            mock_sync.return_value = {"repo_id": "test-repo"}
            mock_cloud.return_value = {"results": []}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            mock_info.assert_called_once()
            mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_sync_skipped_when_not_needed(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.AGENTIC_AUTO_SYNC", True),
            patch("relace_mcp.tools.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.tools.repo.retrieval.cloud_sync_logic") as mock_sync,
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_info.return_value = {"status": {"needs_sync": False}}
            mock_cloud.return_value = {"results": []}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            mock_info.assert_called_once()
            mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_sync_disabled_via_env(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.AGENTIC_AUTO_SYNC", False),
            patch("relace_mcp.tools.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_cloud.return_value = {"results": []}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            mock_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_sync_failure_continues_search(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.tools.repo.retrieval.AGENTIC_AUTO_SYNC", True),
            patch("relace_mcp.tools.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.tools.repo.retrieval.cloud_sync_logic") as mock_sync,
            patch("relace_mcp.tools.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.tools.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_info.return_value = {"status": {"needs_sync": True}}
            mock_sync.return_value = {"error": "Network timeout"}
            mock_cloud.return_value = {"results": []}
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "Still works", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            assert "warnings" in result
            assert any("Auto-sync failed" in w for w in result["warnings"])
            assert result["explanation"] == "Still works"
