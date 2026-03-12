import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.tools.retrieval import agentic_retrieval_logic


@pytest.mark.asyncio
async def test_agentic_retrieval_cloud_search_does_not_block_event_loop(tmp_path):
    config = RelaceConfig(api_key="test", base_dir=str(tmp_path))
    repo_client = MagicMock()

    search_client = MagicMock()
    search_client.api_compat = "relace"

    def blocking_cloud_search_logic(*_args, **_kwargs):
        time.sleep(0.2)
        return {"results": []}

    harness = MagicMock()
    harness.run_async = AsyncMock(return_value={"explanation": "ok", "files": {}, "turns_used": 1})

    with (
        patch("relace_mcp.config.settings.RETRIEVAL_BACKEND", "relace"),
        patch("relace_mcp.config.settings.AGENTIC_AUTO_SYNC", False),
        patch("relace_mcp.tools.retrieval.cloud_search_logic", blocking_cloud_search_logic),
        patch("relace_mcp.lsp.languages.get_lsp_languages", return_value=[]),
        patch("relace_mcp.tools.retrieval.FastAgenticSearchHarness") as mock_harness_cls,
    ):
        mock_harness_cls.return_value = harness

        task = asyncio.create_task(
            agentic_retrieval_logic(
                repo_client,
                search_client,
                config,
                str(tmp_path),
                "query",
            )
        )
        try:
            # If cloud_search_logic runs on the event loop thread, time.sleep(0.2)
            # will delay this small sleep too.
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            elapsed = time.perf_counter() - t0
            assert elapsed < 0.1

            await task
        finally:
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
