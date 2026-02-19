from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import RelaceRepoClient, SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.repo.retrieval import (
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


@pytest.fixture(autouse=True)
def _force_relace_backend():
    with patch("relace_mcp.repo.retrieval.RETRIEVAL_BACKEND", "relace"):
        yield


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
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.AGENTIC_AUTO_SYNC", True),
            patch("relace_mcp.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.repo.retrieval.cloud_sync_logic") as mock_sync,
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.AGENTIC_AUTO_SYNC", True),
            patch("relace_mcp.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.repo.retrieval.cloud_sync_logic") as mock_sync,
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.AGENTIC_AUTO_SYNC", False),
            patch("relace_mcp.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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
            patch("relace_mcp.repo.retrieval.AGENTIC_AUTO_SYNC", True),
            patch("relace_mcp.repo.retrieval.cloud_info_logic") as mock_info,
            patch("relace_mcp.repo.retrieval.cloud_sync_logic") as mock_sync,
            patch("relace_mcp.repo.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
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


class TestChunkHoundIncrementalSync:
    """Stage 0b: ChunkHound schedules background scan on every retrieval (fire-and-forget)."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> RelaceConfig:
        return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    @pytest.fixture
    def mock_search_client(self) -> MagicMock:
        client = MagicMock(spec=SearchLLMClient)
        client.api_compat = "relace"
        return client

    @pytest.mark.asyncio
    async def test_bg_schedule_called_on_every_retrieval(
        self, mock_config: RelaceConfig, mock_search_client: MagicMock, tmp_path: Path
    ) -> None:
        with (
            patch("relace_mcp.repo.retrieval.RETRIEVAL_BACKEND", "chunkhound"),
            patch("relace_mcp.repo.retrieval.schedule_bg_chunkhound_index") as mock_sched,
            patch("relace_mcp.repo.retrieval.chunkhound_search", return_value=[]),
            patch("relace_mcp.repo.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            await agentic_retrieval_logic(
                None, mock_search_client, mock_config, str(tmp_path), "auth logic"
            )
            mock_sched.assert_called_once_with(str(tmp_path))

    @pytest.mark.asyncio
    async def test_bg_schedule_called_twice_for_two_retrievals(
        self, mock_config: RelaceConfig, mock_search_client: MagicMock, tmp_path: Path
    ) -> None:
        """Verifies fire-and-forget fires on every call (no HEAD-based skip)."""
        with (
            patch("relace_mcp.repo.retrieval.RETRIEVAL_BACKEND", "chunkhound"),
            patch("relace_mcp.repo.retrieval.schedule_bg_chunkhound_index") as mock_sched,
            patch("relace_mcp.repo.retrieval.chunkhound_search", return_value=[]),
            patch("relace_mcp.repo.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            for _ in range(2):
                await agentic_retrieval_logic(
                    None, mock_search_client, mock_config, str(tmp_path), "query"
                )
            assert mock_sched.call_count == 2

    @pytest.mark.asyncio
    async def test_stage1_index_missing_does_not_disable_backend(
        self, mock_config: RelaceConfig, mock_search_client: MagicMock, tmp_path: Path
    ) -> None:
        """index_missing in Stage 1 must NOT disable_backend (only cli_not_found should)."""
        from relace_mcp.repo.local.backend import ExternalCLIError

        with (
            patch("relace_mcp.repo.retrieval.RETRIEVAL_BACKEND", "chunkhound"),
            patch("relace_mcp.repo.retrieval.schedule_bg_chunkhound_index"),
            patch(
                "relace_mcp.repo.retrieval.chunkhound_search",
                side_effect=ExternalCLIError(
                    backend="chunkhound", kind="index_missing", message="no index"
                ),
            ),
            patch("relace_mcp.repo.retrieval.disable_backend") as mock_disable,
            patch("relace_mcp.repo.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                None, mock_search_client, mock_config, str(tmp_path), "query"
            )
            mock_disable.assert_not_called()
            assert "warnings" in result
            assert result["explanation"] == "done"

    @pytest.mark.asyncio
    async def test_stage1_index_missing_reschedules_bg_index(
        self, mock_config: RelaceConfig, mock_search_client: MagicMock, tmp_path: Path
    ) -> None:
        """index_missing in Stage 1 must re-schedule a background index build."""
        from relace_mcp.repo.local.backend import ExternalCLIError

        with (
            patch("relace_mcp.repo.retrieval.RETRIEVAL_BACKEND", "chunkhound"),
            patch("relace_mcp.repo.retrieval.schedule_bg_chunkhound_index") as mock_sched,
            patch(
                "relace_mcp.repo.retrieval.chunkhound_search",
                side_effect=ExternalCLIError(
                    backend="chunkhound", kind="index_missing", message="no index"
                ),
            ),
            patch("relace_mcp.repo.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.repo.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness = MagicMock()
            mock_harness.run_async = AsyncMock(
                return_value={"explanation": "done", "files": {}, "turns_used": 1}
            )
            mock_harness_cls.return_value = mock_harness

            await agentic_retrieval_logic(
                None, mock_search_client, mock_config, str(tmp_path), "query"
            )
            # Called once for Stage 0b + once for Stage 1 index_missing recovery
            assert mock_sched.call_count == 2


class TestResolveAutoBackendNoHealthProbe:
    """_resolve_auto_backend must not block via health probes."""

    def test_no_check_backend_health_called(self, tmp_path: Path) -> None:
        from relace_mcp.repo.retrieval import _auto_backend_cache, _resolve_auto_backend

        _auto_backend_cache.clear()
        with (
            patch("relace_mcp.repo.retrieval.shutil.which", return_value=None),
            patch("relace_mcp.repo.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.repo.local.backend.check_backend_health") as mock_health,
        ):
            result = _resolve_auto_backend(str(tmp_path))
        assert result == "relace"
        mock_health.assert_not_called()

    def test_returns_first_available_cli(self, tmp_path: Path) -> None:
        from relace_mcp.repo.retrieval import _auto_backend_cache, _resolve_auto_backend

        _auto_backend_cache.clear()
        with (
            patch(
                "relace_mcp.repo.retrieval.shutil.which",
                side_effect=lambda name: "/usr/bin/" + name if name == "chunkhound" else None,
            ),
            patch("relace_mcp.repo.retrieval.is_backend_disabled", return_value=False),
        ):
            result = _resolve_auto_backend(str(tmp_path))
        assert result == "chunkhound"


class TestChunkHoundIndexFileBug1:
    """Regression: chunkhound_index_file must use kind='cli_not_found' for missing CLI."""

    def test_file_not_found_produces_cli_not_found_kind(self, tmp_path: Path) -> None:
        from relace_mcp.repo.local.backend import ExternalCLIError, chunkhound_index_file

        with patch(
            "relace_mcp.repo.local.backend._ensure_chunkhound_index",
            side_effect=RuntimeError("chunkhound CLI not found"),
        ) as mock_ensure:
            mock_ensure.side_effect.__cause__ = None
            # Simulate FileNotFoundError as __cause__
            cause = FileNotFoundError("no such file")
            err = RuntimeError("chunkhound CLI not found")
            err.__cause__ = cause
            mock_ensure.side_effect = err

            with pytest.raises(ExternalCLIError) as exc_info:
                chunkhound_index_file("/some/file.py", str(tmp_path))
            assert exc_info.value.kind == "cli_not_found"

    def test_nonzero_exit_produces_nonzero_exit_kind(self, tmp_path: Path) -> None:
        from relace_mcp.repo.local.backend import ExternalCLIError, chunkhound_index_file

        plain_err = RuntimeError("chunkhound index failed: some error")
        with patch(
            "relace_mcp.repo.local.backend._ensure_chunkhound_index",
            side_effect=plain_err,
        ):
            with pytest.raises(ExternalCLIError) as exc_info:
                chunkhound_index_file("/some/file.py", str(tmp_path))
            assert exc_info.value.kind == "nonzero_exit"


class TestChunkHoundSearchAllowAutoIndex:
    """chunkhound_search with allow_auto_index=False must raise immediately on index_missing."""

    def test_raises_index_missing_without_blocking(self, tmp_path: Path) -> None:
        from relace_mcp.repo.local.backend import ExternalCLIError, chunkhound_search

        missing_msg = "database not found, run chunkhound index"
        with (
            patch(
                "relace_mcp.repo.local.backend._run_cli_text",
                side_effect=RuntimeError(missing_msg),
            ),
            patch("relace_mcp.repo.local.backend._ensure_chunkhound_index") as mock_ensure,
        ):
            with pytest.raises(ExternalCLIError) as exc_info:
                chunkhound_search("auth", base_dir=str(tmp_path), allow_auto_index=False)
            assert exc_info.value.kind == "index_missing"
            mock_ensure.assert_not_called()


class TestScheduleBgDedup:
    """schedule_bg_chunkhound_index dedup + rerun semantics."""

    @pytest.mark.asyncio
    async def test_dedup_sets_rerun_flag_when_task_running(self) -> None:
        import asyncio

        from relace_mcp.repo.local.backend import (
            _bg_index_rerun,
            _bg_index_tasks,
            schedule_bg_chunkhound_index,
        )

        base_dir = "/fake/repo/dedup"
        key = (base_dir, "chunkhound")
        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)

        # Install a fake running task
        async def _never_done() -> None:
            await asyncio.sleep(10)

        running_task = asyncio.create_task(_never_done())
        _bg_index_tasks[key] = running_task

        try:
            schedule_bg_chunkhound_index(base_dir)
            assert _bg_index_rerun.get(key) is True
        finally:
            running_task.cancel()
            _bg_index_tasks.pop(key, None)
            _bg_index_rerun.pop(key, None)

    @pytest.mark.asyncio
    async def test_rerun_after_done_reschedules(self) -> None:
        import asyncio

        from relace_mcp.repo.local.backend import (
            _bg_index_rerun,
            _bg_index_tasks,
            schedule_bg_chunkhound_index,
        )

        base_dir = "/fake/repo/rerun"
        key = (base_dir, "chunkhound")
        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)

        call_count = 0

        async def _fast_index(bd: str) -> None:
            nonlocal call_count
            call_count += 1

        with patch(
            "relace_mcp.repo.local.backend._async_run_chunkhound_index",
            side_effect=_fast_index,
        ):
            schedule_bg_chunkhound_index(base_dir)
            _bg_index_rerun[key] = True
            first_task = _bg_index_tasks[key]
            await first_task
            await asyncio.sleep(0)  # yield to allow done-callback to fire

        assert call_count == 2, "rerun flag should trigger a second schedule"

        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)


class TestScheduleBgCodannaQueue:
    @pytest.mark.asyncio
    async def test_queues_pending_paths_instead_of_last_write_wins(self) -> None:
        import asyncio

        from relace_mcp.repo.local.backend import (
            _bg_codanna_pending,
            _bg_index_rerun,
            _bg_index_tasks,
            schedule_bg_codanna_index,
        )

        base_dir = "/fake/repo/codanna"
        key = (base_dir, "codanna")
        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)
        _bg_codanna_pending.pop(key, None)

        first_path = f"{base_dir}/a.py"
        second_path = f"{base_dir}/b.py"
        third_path = f"{base_dir}/c.py"

        started: list[str] = []
        unblock = asyncio.Event()

        async def _fake_index(fp: str, bd: str) -> None:
            started.append(fp)
            if fp == first_path:
                await unblock.wait()

        try:
            with patch(
                "relace_mcp.repo.local.backend._async_run_codanna_index",
                side_effect=_fake_index,
            ):
                schedule_bg_codanna_index(first_path, base_dir)
                await asyncio.sleep(0)  # let first task start
                schedule_bg_codanna_index(second_path, base_dir)
                schedule_bg_codanna_index(third_path, base_dir)

                unblock.set()

                async def _wait_for_all() -> None:
                    while len(set(started)) < 3:
                        await asyncio.sleep(0)

                await asyncio.wait_for(_wait_for_all(), timeout=1)

                last_task = _bg_index_tasks.get(key)
                if last_task is not None:
                    await last_task
                    await asyncio.sleep(0)
        finally:
            task = _bg_index_tasks.get(key)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            _bg_index_tasks.pop(key, None)
            _bg_index_rerun.pop(key, None)
            _bg_codanna_pending.pop(key, None)

        assert set(started) == {first_path, second_path, third_path}
