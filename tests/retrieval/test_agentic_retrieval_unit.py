import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import RelaceRepoClient, SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.config import settings as settings_mod
from relace_mcp.repo.freshness import FreshnessStatus
from relace_mcp.search import retrieval as _retrieval_mod
from relace_mcp.search.prompt_messages import format_hints_list
from relace_mcp.search.retrieval import _compact_semantic_hints, agentic_retrieval_logic


async def _wait_for_guidance(
    provider: Callable[[int], list[str]],
    turn: int,
    *,
    timeout: float = 2.0,
) -> list[str]:
    """Poll `provider(turn)` until it returns a non-empty list or timeout elapses."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        messages = provider(turn)
        if messages:
            return messages
        await asyncio.sleep(0.01)
    return provider(turn)


async def _drain_retrieval_tasks(*, timeout: float = 2.0) -> None:
    """Await all currently tracked background retrieval tasks to completion."""
    tasks = [t for t in _retrieval_mod._background_retrieval_tasks if not t.done()]
    if tasks:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout,
        )


@pytest.fixture(autouse=True)
def _default_retrieval_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod, "RETRIEVAL_BACKEND", "relace")
    monkeypatch.setattr(settings_mod, "RETRIEVAL_HINT_POLICY", "prefer-stale")


class TestFormatHintsList:
    def test_formats_results_correctly(self) -> None:
        hints = [
            {"filename": "src/auth.py", "score": 0.85},
            {"filename": "src/login.py", "score": 0.72},
        ]
        result = format_hints_list(hints)

        assert "src/auth.py (score: 0.85)" in result
        assert "src/login.py (score: 0.72)" in result

    def test_empty_returns_empty(self) -> None:
        assert format_hints_list([]) == ""

    def test_respects_max_hints_via_compact(self) -> None:
        results = [{"filename": f"file{i}.py", "score": 0.9 - i * 0.1} for i in range(10)]
        hints = _compact_semantic_hints(results, 3)
        result = format_hints_list(hints)

        assert "file0.py" in result
        assert "file1.py" in result
        assert "file2.py" in result
        assert "file3.py" not in result

    def test_handles_file_key_fallback(self) -> None:
        results = [{"file": "src/utils.py", "score": 0.65}]
        hints = _compact_semantic_hints(results, 8)
        result = format_hints_list(hints)

        assert "src/utils.py (score: 0.65)" in result


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

    @pytest.fixture
    def mock_harness(self) -> MagicMock:
        harness = MagicMock()
        harness.run_async = AsyncMock(
            return_value={"explanation": "Found files", "files": {}, "turns_used": 1}
        )
        return harness

    @pytest.mark.asyncio
    async def test_fallback_on_cloud_error(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        class PollingHarness:
            def __init__(self, *_args, **kwargs) -> None:
                self._provider = kwargs.get("runtime_user_messages_provider")

            async def run_async(self, **_kwargs) -> dict[str, object]:
                assert callable(self._provider)
                assert self._provider(0) == []
                await _drain_retrieval_tasks()
                assert self._provider(1) == []
                return {"explanation": "Found files", "files": {}, "turns_used": 2}

        with (
            patch(
                "relace_mcp.search.retrieval.classify_cloud_index_freshness",
                return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
            ),
            patch("relace_mcp.search.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness", PollingHarness),
        ):
            mock_cloud.return_value = {"error": "Network error", "results": []}

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "find auth logic",
            )

            assert "warnings" in result
            assert any("Cloud search failed" in warning for warning in result["warnings"])
            assert result["semantic_hints_used"] == 0
            assert result["semantic_hints"] == []

    @pytest.mark.asyncio
    async def test_hints_injected_in_prompt(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        captured_kwargs: dict[str, object] = {}

        class PollingHarness:
            def __init__(self, *_args, **kwargs) -> None:
                captured_kwargs.update(kwargs)
                self._provider = kwargs.get("runtime_user_messages_provider")

            async def run_async(self, **_kwargs) -> dict[str, object]:
                assert callable(self._provider)
                assert self._provider(0) == []
                assert await _wait_for_guidance(self._provider, 1)
                return {"explanation": "Found files", "files": {}, "turns_used": 2}

        with (
            patch(
                "relace_mcp.search.retrieval.classify_cloud_index_freshness",
                return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
            ),
            patch("relace_mcp.search.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness", PollingHarness),
        ):
            mock_cloud.return_value = {
                "results": [
                    {"filename": "src/auth.py", "score": 0.85},
                    {"filename": "src/login.py", "score": 0.72},
                ]
            }

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "find authentication",
            )

            assert "prompts" in captured_kwargs
            assert callable(captured_kwargs.get("runtime_user_messages_provider"))

            assert result["semantic_hints_used"] == 2
            assert result["hint_policy"] == "prefer-stale"
            assert result["hints_index_freshness"] == "fresh"
            assert result["semantic_hints"] == [
                {"filename": "/repo/src/auth.py", "score": 0.85},
                {"filename": "/repo/src/login.py", "score": 0.72},
            ]

    @pytest.mark.asyncio
    async def test_happy_path(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        class PollingHarness:
            def __init__(self, *_args, **kwargs) -> None:
                self._provider = kwargs.get("runtime_user_messages_provider")

            async def run_async(self, **_kwargs) -> dict[str, object]:
                assert callable(self._provider)
                assert self._provider(0) == []
                assert await _wait_for_guidance(self._provider, 1)
                return {
                    "explanation": "Result",
                    "files": {"src/core.py": [[1, 10]]},
                    "turns_used": 2,
                }

        with (
            patch(
                "relace_mcp.search.retrieval.classify_cloud_index_freshness",
                return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
            ),
            patch("relace_mcp.search.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness", PollingHarness),
        ):
            mock_cloud.return_value = {"results": [{"filename": "src/core.py", "score": 0.9}]}

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            assert result["explanation"] == "Result"
            assert "src/core.py" in result["files"]
            assert result["semantic_hints_used"] == 1
            assert result["background_refresh_scheduled"] is False
            assert "trace_id" in result

    @pytest.mark.asyncio
    async def test_relace_stale_prefer_stale_uses_hints_without_sync(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        captured_kwargs: dict[str, object] = {}

        class PollingHarness:
            def __init__(self, *_args, **kwargs) -> None:
                captured_kwargs.update(kwargs)
                self._provider = kwargs.get("runtime_user_messages_provider")

            async def run_async(self, **_kwargs) -> dict[str, object]:
                assert callable(self._provider)
                assert self._provider(0) == []
                assert await _wait_for_guidance(self._provider, 1)
                return {"explanation": "Found files", "files": {}, "turns_used": 2}

        with (
            patch(
                "relace_mcp.search.retrieval.classify_cloud_index_freshness",
                return_value=FreshnessStatus("stale", True, True, "git_head_changed"),
            ),
            patch("relace_mcp.search.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness", PollingHarness),
        ):
            mock_cloud.return_value = {"results": [{"filename": "src/core.py", "score": 0.9}]}

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            mock_cloud.assert_called_once()
            assert result["semantic_hints_used"] == 1
            assert result["hints_index_freshness"] == "stale"
            assert any(
                "Using stale Relace semantic hints" in warning for warning in result["warnings"]
            )
            assert callable(captured_kwargs.get("runtime_user_messages_provider"))

    @pytest.mark.asyncio
    async def test_relace_stale_strict_skips_hints(
        self,
        mock_config: RelaceConfig,
        mock_repo_client: MagicMock,
        mock_search_client: MagicMock,
        mock_harness: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.config.settings.RETRIEVAL_HINT_POLICY", "strict"),
            patch(
                "relace_mcp.search.retrieval.classify_cloud_index_freshness",
                return_value=FreshnessStatus("stale", True, True, "git_head_changed"),
            ),
            patch("relace_mcp.search.retrieval.cloud_search_logic") as mock_cloud,
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                str(tmp_path),
                "query",
            )

            mock_cloud.assert_not_called()
            assert result["semantic_hints_used"] == 0
            assert result["hints_index_freshness"] == "stale"
            assert any(
                "MCP_RETRIEVAL_HINT_POLICY=strict" in warning for warning in result["warnings"]
            )

    @pytest.mark.asyncio
    async def test_chunkhound_stale_uses_hints_and_schedules_refresh(
        self,
        mock_config: RelaceConfig,
        mock_search_client: MagicMock,
        mock_harness: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.config.settings.RETRIEVAL_BACKEND", "chunkhound"),
            patch(
                "relace_mcp.search.retrieval.classify_local_index_freshness",
                return_value=FreshnessStatus("stale", True, True, "git_head_changed"),
            ),
            patch("relace_mcp.search.retrieval.chunkhound_search", return_value=[]),
            patch("relace_mcp.search.retrieval.schedule_bg_chunkhound_index") as mock_schedule,
            patch("relace_mcp.search.retrieval.shutil.which", return_value="/usr/bin/chunkhound"),
            patch("relace_mcp.search.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                None, mock_search_client, mock_config, str(tmp_path), "auth logic"
            )
            mock_schedule.assert_called_once_with(str(tmp_path))
            assert result["background_refresh_scheduled"] is True
            assert result["hints_index_freshness"] == "stale"
            assert any(
                "Using stale ChunkHound semantic hints" in warning for warning in result["warnings"]
            )

    @pytest.mark.asyncio
    async def test_codanna_missing_strict_schedules_refresh_without_hints(
        self,
        mock_config: RelaceConfig,
        mock_search_client: MagicMock,
        mock_harness: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch("relace_mcp.config.settings.RETRIEVAL_BACKEND", "codanna"),
            patch("relace_mcp.config.settings.RETRIEVAL_HINT_POLICY", "strict"),
            patch(
                "relace_mcp.search.retrieval.classify_local_index_freshness",
                return_value=FreshnessStatus("missing", False, True, "index_dir_missing"),
            ),
            patch("relace_mcp.search.retrieval.schedule_bg_codanna_full_index") as mock_schedule,
            patch("relace_mcp.search.retrieval.codanna_search") as mock_search,
            patch("relace_mcp.search.retrieval.shutil.which", return_value="/usr/bin/codanna"),
            patch("relace_mcp.search.retrieval.is_backend_disabled", return_value=False),
            patch("relace_mcp.search.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
        ):
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                None, mock_search_client, mock_config, str(tmp_path), "query"
            )
            mock_schedule.assert_called_once_with(str(tmp_path))
            mock_search.assert_not_called()
            assert result["semantic_hints_used"] == 0
            assert result["background_refresh_scheduled"] is True
            assert result["hints_index_freshness"] == "missing"

    @pytest.mark.asyncio
    async def test_repo_client_none_still_works(
        self,
        mock_config: RelaceConfig,
        mock_search_client: MagicMock,
        mock_harness: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch("relace_mcp.search.retrieval.FastAgenticSearchHarness") as mock_harness_cls:
            mock_harness_cls.return_value = mock_harness

            result = await agentic_retrieval_logic(
                None, mock_search_client, mock_config, str(tmp_path), "find auth"
            )

            assert "explanation" in result
            assert result["semantic_hints_used"] == 0
            assert result["hints_index_freshness"] == "missing"


class TestChunkHoundIndexFileBug1:
    """Regression: chunkhound_index_file must use kind='cli_not_found' for missing CLI."""

    def test_file_not_found_produces_cli_not_found_kind(self, tmp_path: Path) -> None:
        from relace_mcp.repo.backends import ExternalCLIError, chunkhound_index_file

        with patch(
            "relace_mcp.repo.backends.chunkhound._ensure_chunkhound_index",
            side_effect=RuntimeError("chunkhound CLI not found"),
        ) as mock_ensure:
            mock_ensure.side_effect.__cause__ = None
            cause = FileNotFoundError("no such file")
            err = RuntimeError("chunkhound CLI not found")
            err.__cause__ = cause
            mock_ensure.side_effect = err

            with pytest.raises(ExternalCLIError) as exc_info:
                chunkhound_index_file("/some/file.py", str(tmp_path))
            assert exc_info.value.kind == "cli_not_found"

    def test_nonzero_exit_produces_nonzero_exit_kind(self, tmp_path: Path) -> None:
        from relace_mcp.repo.backends import ExternalCLIError, chunkhound_index_file

        plain_err = RuntimeError("chunkhound index failed: some error")
        with patch(
            "relace_mcp.repo.backends.chunkhound._ensure_chunkhound_index",
            side_effect=plain_err,
        ):
            with pytest.raises(ExternalCLIError) as exc_info:
                chunkhound_index_file("/some/file.py", str(tmp_path))
            assert exc_info.value.kind == "nonzero_exit"


class TestChunkHoundSearchAllowAutoIndex:
    """chunkhound_search with allow_auto_index=False must raise immediately on index_missing."""

    def test_raises_index_missing_without_blocking(self, tmp_path: Path) -> None:
        from relace_mcp.repo.backends import ExternalCLIError, chunkhound_search

        missing_msg = "database not found, run chunkhound index"
        with (
            patch(
                "relace_mcp.repo.backends.chunkhound._run_cli_text",
                side_effect=RuntimeError(missing_msg),
            ),
            patch("relace_mcp.repo.backends.chunkhound._ensure_chunkhound_index") as mock_ensure,
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

        from relace_mcp.repo.backends import schedule_bg_chunkhound_index
        from relace_mcp.repo.backends.registry import _bg_index_rerun, _bg_index_tasks

        base_dir = "/fake/repo/dedup"
        key = (base_dir, "chunkhound")
        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)

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

        from relace_mcp.repo.backends import schedule_bg_chunkhound_index
        from relace_mcp.repo.backends.registry import _bg_index_rerun, _bg_index_tasks

        base_dir = "/fake/repo/rerun"
        key = (base_dir, "chunkhound")
        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)

        call_count = 0

        async def _fast_index(_bd: str) -> None:
            nonlocal call_count
            call_count += 1

        with patch(
            "relace_mcp.repo.backends.chunkhound._async_run_chunkhound_index",
            side_effect=_fast_index,
        ):
            schedule_bg_chunkhound_index(base_dir)
            _bg_index_rerun[key] = True
            first_task = _bg_index_tasks[key]
            await first_task
            for _ in range(10):
                await asyncio.sleep(0)
            second_task = _bg_index_tasks.get(key)
            if second_task is not None and not second_task.done():
                await asyncio.wait_for(second_task, timeout=2)

        assert call_count == 2

        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)


class TestScheduleBgCodannaRefresh:
    @pytest.mark.asyncio
    async def test_running_task_sets_rerun_flag(self) -> None:
        import asyncio

        from relace_mcp.repo.backends import schedule_bg_codanna_index
        from relace_mcp.repo.backends.registry import _bg_index_rerun, _bg_index_tasks

        base_dir = "/fake/repo/codanna"
        key = (base_dir, "codanna")
        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)

        async def _never_done() -> None:
            await asyncio.sleep(10)

        running_task = asyncio.create_task(_never_done())
        _bg_index_tasks[key] = running_task

        try:
            schedule_bg_codanna_index(f"{base_dir}/a.py", base_dir)
            assert _bg_index_rerun.get(key) is True
        finally:
            running_task.cancel()
            _bg_index_tasks.pop(key, None)
            _bg_index_rerun.pop(key, None)
