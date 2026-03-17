from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import RelaceRepoClient, SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.repo.freshness import FreshnessStatus
from relace_mcp.search.retrieval import agentic_retrieval_logic

_RETRIEVAL_MOD = "relace_mcp.search.retrieval"
_SETTINGS_MOD = "relace_mcp.config.settings"

HARNESS_RESULT = {
    "explanation": "test",
    "files": {"src/main.py": [[1, 10], [20, 30]]},
    "turns_used": 1,
}

SEMANTIC_RESULTS = [
    {"filename": "src/main.py", "score": 0.95},
    {"filename": "src/utils.py", "score": 0.80},
]


@pytest.fixture
def mock_config(tmp_path):
    return RelaceConfig(api_key="test-key-xxxxx", base_dir=str(tmp_path))


@pytest.fixture
def mock_repo_client():
    return MagicMock(spec=RelaceRepoClient)


@pytest.fixture
def mock_search_client():
    client = MagicMock(spec=SearchLLMClient)
    client.api_compat = "relace"
    return client


@pytest.fixture
def mock_harness():
    with patch(f"{_RETRIEVAL_MOD}.FastAgenticSearchHarness") as cls:
        instance = MagicMock()
        instance.run_async = AsyncMock(return_value={**HARNESS_RESULT})
        cls.return_value = instance
        yield cls


@pytest.fixture
def mock_cloud_search():
    with patch(f"{_RETRIEVAL_MOD}.cloud_search_logic") as m:
        m.return_value = {"results": list(SEMANTIC_RESULTS)}
        yield m


@pytest.fixture
def mock_is_backend_disabled():
    with patch(f"{_RETRIEVAL_MOD}.is_backend_disabled", return_value=False) as m:
        yield m


@pytest.fixture
def mock_lsp_languages():
    with patch("relace_mcp.lsp.languages.get_lsp_languages", return_value=frozenset()) as m:
        yield m


@pytest.fixture
def all_mocks(mock_harness, mock_cloud_search, mock_is_backend_disabled, mock_lsp_languages):
    return {
        "harness_cls": mock_harness,
        "cloud_search": mock_cloud_search,
        "is_backend_disabled": mock_is_backend_disabled,
        "lsp_languages": mock_lsp_languages,
    }


class TestRetrievalMCPContract:
    @pytest.mark.asyncio
    async def test_return_dict_has_required_keys(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(
            f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
            return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )
        for key in (
            "explanation",
            "files",
            "turns_used",
            "trace_id",
            "semantic_hints_used",
            "hint_policy",
            "hints_index_freshness",
            "background_refresh_scheduled",
        ):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_files_is_dict_of_str_to_list_of_pairs(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(
            f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
            return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )
        files = result["files"]
        assert isinstance(files, dict)
        for path, ranges in files.items():
            assert isinstance(path, str)
            assert isinstance(ranges, list)
            for pair in ranges:
                assert isinstance(pair, list)
                assert len(pair) == 2

    @pytest.mark.asyncio
    async def test_trace_id_is_nonempty_string(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(
            f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
            return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )
        assert isinstance(result["trace_id"], str)
        assert len(result["trace_id"]) > 0

    @pytest.mark.asyncio
    async def test_semantic_hints_used_is_nonneg_int(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(
            f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
            return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )
        assert isinstance(result["semantic_hints_used"], int)
        assert result["semantic_hints_used"] >= 0


class TestRetrievalOrchestration:
    @pytest.mark.asyncio
    async def test_cloud_search_called_before_harness(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        call_order: list[str] = []
        all_mocks["cloud_search"].side_effect = lambda *a, **kw: (
            call_order.append("cloud_search") or {"results": list(SEMANTIC_RESULTS)}
        )
        harness_instance = all_mocks["harness_cls"].return_value

        async def tracked_run(*a, **kw):
            call_order.append("harness_run")
            return {**HARNESS_RESULT}

        harness_instance.run_async = AsyncMock(side_effect=tracked_run)

        with patch(
            f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
            return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
        ):
            await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )
        assert call_order.index("cloud_search") < call_order.index("harness_run")

    @pytest.mark.asyncio
    async def test_relace_stale_prefer_stale_uses_hints_without_sync(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with (
            patch(f"{_SETTINGS_MOD}.RETRIEVAL_HINT_POLICY", "prefer-stale"),
            patch(
                f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
                return_value=FreshnessStatus("stale", True, True, "git_head_changed"),
            ),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )

        all_mocks["cloud_search"].assert_called_once()
        assert result["semantic_hints_used"] == len(SEMANTIC_RESULTS)
        assert result["hints_index_freshness"] == "stale"
        assert any("Using stale Relace semantic hints" in warning for warning in result["warnings"])

    @pytest.mark.asyncio
    async def test_relace_stale_strict_skips_hints(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with (
            patch(f"{_SETTINGS_MOD}.RETRIEVAL_HINT_POLICY", "strict"),
            patch(
                f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
                return_value=FreshnessStatus("stale", True, True, "git_head_changed"),
            ),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )

        all_mocks["cloud_search"].assert_not_called()
        assert result["semantic_hints_used"] == 0
        assert result["hints_index_freshness"] == "stale"
        assert any("MCP_RETRIEVAL_HINT_POLICY=strict" in warning for warning in result["warnings"])

    @pytest.mark.asyncio
    async def test_repo_client_none_still_works(self, mock_config, mock_search_client, all_mocks):
        result = await agentic_retrieval_logic(
            None, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        assert "explanation" in result
        assert result["semantic_hints_used"] == 0
        all_mocks["cloud_search"].assert_not_called()

    @pytest.mark.asyncio
    async def test_harness_prompt_contains_semantic_hints_when_results(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(
            f"{_RETRIEVAL_MOD}.classify_cloud_index_freshness",
            return_value=FreshnessStatus("fresh", True, False, "up_to_date"),
        ):
            await agentic_retrieval_logic(
                mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
            )
        _, kwargs = all_mocks["harness_cls"].call_args
        assert kwargs.get("retrieval") is True

        harness_instance = all_mocks["harness_cls"].return_value
        run_kwargs = harness_instance.run_async.call_args.kwargs
        assert "semantic_hints" in run_kwargs.get("semantic_hints_section", "")


class TestRetrievalBackendDispatch:
    @pytest.mark.asyncio
    async def test_none_backend_skips_semantic_retrieval(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(f"{_SETTINGS_MOD}.RETRIEVAL_BACKEND", "none"):
            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        all_mocks["cloud_search"].assert_not_called()
        assert result["semantic_hints_used"] == 0
        assert result["hints_index_freshness"] == "missing"

    @pytest.mark.asyncio
    async def test_chunkhound_stale_prefer_stale_uses_hints_and_schedules_refresh(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with (
            patch(f"{_SETTINGS_MOD}.RETRIEVAL_BACKEND", "chunkhound"),
            patch(
                f"{_RETRIEVAL_MOD}.classify_local_index_freshness",
                return_value=FreshnessStatus("stale", True, True, "git_head_changed"),
            ),
            patch(
                f"{_RETRIEVAL_MOD}.chunkhound_search", return_value=list(SEMANTIC_RESULTS)
            ) as m_ch,
            patch(f"{_RETRIEVAL_MOD}.schedule_bg_chunkhound_index") as mock_schedule,
            patch(f"{_RETRIEVAL_MOD}.shutil.which", return_value="/usr/bin/chunkhound"),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        m_ch.assert_called_once()
        mock_schedule.assert_called_once_with(mock_config.base_dir)
        assert result["semantic_hints_used"] == len(SEMANTIC_RESULTS)
        assert result["background_refresh_scheduled"] is True
        assert result["hints_index_freshness"] == "stale"

    @pytest.mark.asyncio
    async def test_codanna_missing_strict_skips_hints_but_schedules_refresh(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with (
            patch(f"{_SETTINGS_MOD}.RETRIEVAL_BACKEND", "codanna"),
            patch(f"{_SETTINGS_MOD}.RETRIEVAL_HINT_POLICY", "strict"),
            patch(
                f"{_RETRIEVAL_MOD}.classify_local_index_freshness",
                return_value=FreshnessStatus("missing", False, True, "index_dir_missing"),
            ),
            patch(f"{_RETRIEVAL_MOD}.schedule_bg_codanna_full_index") as mock_schedule,
            patch(f"{_RETRIEVAL_MOD}.codanna_search") as m_cd,
            patch(f"{_RETRIEVAL_MOD}.shutil.which", return_value="/usr/bin/codanna"),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        m_cd.assert_not_called()
        mock_schedule.assert_called_once_with(mock_config.base_dir)
        assert result["semantic_hints_used"] == 0
        assert result["background_refresh_scheduled"] is True
        assert result["hints_index_freshness"] == "missing"
