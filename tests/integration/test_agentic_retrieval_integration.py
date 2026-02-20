from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import RelaceRepoClient, SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.retrieval import agentic_retrieval_logic

_RETRIEVAL_MOD = "relace_mcp.tools.retrieval"

HARNESS_RESULT = {
    "explanation": "test",
    "files": {"src/main.py": [[1, 10], [20, 30]]},
    "turns_used": 1,
}

CLOUD_SEARCH_RESULTS = [
    {"filename": "src/main.py", "score": 0.95},
    {"filename": "src/utils.py", "score": 0.80},
]


@pytest.fixture(autouse=True)
def _force_relace_backend():  # pyright: ignore[reportUnusedFunction]
    with patch(f"{_RETRIEVAL_MOD}.RETRIEVAL_BACKEND", "relace"):
        yield


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
        m.return_value = {"results": list(CLOUD_SEARCH_RESULTS)}
        yield m


@pytest.fixture
def mock_cloud_info():
    with patch(f"{_RETRIEVAL_MOD}.cloud_info_logic") as m:
        m.return_value = {"status": {"needs_sync": False}}
        yield m


@pytest.fixture
def mock_cloud_sync():
    with patch(f"{_RETRIEVAL_MOD}.cloud_sync_logic") as m:
        m.return_value = {}
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
def all_mocks(
    mock_harness,
    mock_cloud_search,
    mock_cloud_info,
    mock_cloud_sync,
    mock_is_backend_disabled,
    mock_lsp_languages,
):
    return {
        "harness_cls": mock_harness,
        "cloud_search": mock_cloud_search,
        "cloud_info": mock_cloud_info,
        "cloud_sync": mock_cloud_sync,
        "is_backend_disabled": mock_is_backend_disabled,
        "lsp_languages": mock_lsp_languages,
    }


class TestRetrievalMCPContract:
    @pytest.mark.asyncio
    async def test_return_dict_has_required_keys(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        result = await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        for key in ("explanation", "files", "turns_used", "trace_id", "cloud_hints_used"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_files_is_dict_of_str_to_list_of_pairs(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
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
        result = await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        assert isinstance(result["trace_id"], str)
        assert len(result["trace_id"]) > 0

    @pytest.mark.asyncio
    async def test_cloud_hints_used_is_nonneg_int(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        result = await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        assert isinstance(result["cloud_hints_used"], int)
        assert result["cloud_hints_used"] >= 0

    @pytest.mark.asyncio
    async def test_warnings_key_present_when_warnings_exist(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        all_mocks["cloud_search"].return_value = {"error": "boom"}
        result = await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        assert "warnings" in result
        assert isinstance(result["warnings"], list)
        assert all(isinstance(w, str) for w in result["warnings"])


class TestRetrievalOrchestration:
    @pytest.mark.asyncio
    async def test_cloud_search_called_before_harness(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        call_order: list[str] = []
        all_mocks["cloud_search"].side_effect = lambda *a, **kw: (
            call_order.append("cloud_search") or {"results": list(CLOUD_SEARCH_RESULTS)}
        )
        harness_instance = all_mocks["harness_cls"].return_value

        async def tracked_run(*a, **kw):
            call_order.append("harness_run")
            return {**HARNESS_RESULT}

        harness_instance.run_async = AsyncMock(side_effect=tracked_run)

        await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        assert call_order.index("cloud_search") < call_order.index("harness_run")

    @pytest.mark.asyncio
    async def test_auto_sync_triggered_when_needs_sync(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        all_mocks["cloud_info"].return_value = {"status": {"needs_sync": True}}
        with patch(f"{_RETRIEVAL_MOD}.AGENTIC_AUTO_SYNC", True):
            await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        all_mocks["cloud_sync"].assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_client_none_still_works(self, mock_config, mock_search_client, all_mocks):
        result = await agentic_retrieval_logic(
            None, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        assert "explanation" in result
        assert result["cloud_hints_used"] == 0
        all_mocks["cloud_search"].assert_not_called()

    @pytest.mark.asyncio
    async def test_harness_prompt_contains_semantic_hints_when_cloud_results(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        _, kwargs = all_mocks["harness_cls"].call_args
        prompt = kwargs["user_prompt_override"]
        assert "semantic_hints" in prompt

    @pytest.mark.asyncio
    async def test_harness_prompt_no_semantic_hints_when_no_cloud_results(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        all_mocks["cloud_search"].return_value = {"results": []}
        await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        _, kwargs = all_mocks["harness_cls"].call_args
        prompt = kwargs["user_prompt_override"]
        assert "semantic_hints" not in prompt


class TestRetrievalBackendDispatch:
    @pytest.mark.asyncio
    async def test_relace_backend_calls_cloud_search(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        await agentic_retrieval_logic(
            mock_repo_client, mock_search_client, mock_config, mock_config.base_dir, "find auth"
        )
        all_mocks["cloud_search"].assert_called_once()

    @pytest.mark.asyncio
    async def test_none_backend_skips_semantic_retrieval(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with patch(f"{_RETRIEVAL_MOD}.RETRIEVAL_BACKEND", "none"):
            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        all_mocks["cloud_search"].assert_not_called()
        assert result["cloud_hints_used"] == 0

    @pytest.mark.asyncio
    async def test_chunkhound_backend_calls_chunkhound_search(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with (
            patch(f"{_RETRIEVAL_MOD}.RETRIEVAL_BACKEND", "chunkhound"),
            patch(
                f"{_RETRIEVAL_MOD}.chunkhound_search", return_value=list(CLOUD_SEARCH_RESULTS)
            ) as m_ch,
            patch(f"{_RETRIEVAL_MOD}.chunkhound_auto_reindex", return_value={"action": "skipped"}),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        m_ch.assert_called_once()
        assert result["cloud_hints_used"] == len(CLOUD_SEARCH_RESULTS)

    @pytest.mark.asyncio
    async def test_codanna_backend_calls_codanna_search(
        self, mock_config, mock_repo_client, mock_search_client, all_mocks
    ):
        with (
            patch(f"{_RETRIEVAL_MOD}.RETRIEVAL_BACKEND", "codanna"),
            patch(
                f"{_RETRIEVAL_MOD}.codanna_search", return_value=list(CLOUD_SEARCH_RESULTS)
            ) as m_cd,
            patch(f"{_RETRIEVAL_MOD}.codanna_auto_reindex", return_value={"action": "skipped"}),
        ):
            result = await agentic_retrieval_logic(
                mock_repo_client,
                mock_search_client,
                mock_config,
                mock_config.base_dir,
                "find auth",
            )
        m_cd.assert_called_once()
        assert result["cloud_hints_used"] == len(CLOUD_SEARCH_RESULTS)
