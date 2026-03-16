import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from benchmark.runner.executor import BenchmarkRunner
from benchmark.schemas import DatasetCase
from relace_mcp.config import RelaceConfig


def test_execute_search_writes_trace_meta_without_turns_log(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir()

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    runner = BenchmarkRunner(config, progress=False, trace=True, search_mode="indexed")
    runner._traces_dir = traces_dir

    case = DatasetCase(
        id="case_1",
        query="find auth logic",
        repo="example/repo",
        base_commit="deadbeef",
    )

    async def fake_agentic_retrieval_logic(*args, **kwargs):
        return {
            "explanation": "Found files",
            "files": {},
            "turns_used": 1,
            "retrieval_backend": "chunkhound",
            "retrieval_latency_s": 0.123,
            "hint_policy": "prefer-stale",
            "hints_index_freshness": "fresh",
            "background_refresh_scheduled": False,
            "reindex_action": None,
            "semantic_hints_used": 2,
            "semantic_hints": [
                {"filename": "src/auth.py", "score": 0.91},
                {"filename": "src/login.py", "score": 0.73},
            ],
        }

    with (
        patch("benchmark.runner.executor.SearchLLMClient", return_value=MagicMock()),
        patch("benchmark.runner.executor.get_lsp_languages", return_value=frozenset()),
        patch("benchmark.runner.preflight.check_retrieval_backend", return_value={"ok": True}),
        patch("relace_mcp.clients.RelaceRepoClient", return_value=MagicMock()),
        patch(
            "relace_mcp.tools.retrieval.agentic_retrieval_logic", new=fake_agentic_retrieval_logic
        ),
    ):
        runner._execute_search(case, repo_path)

    meta_path = traces_dir / "case_1.meta.json"
    trace_path = traces_dir / "case_1.jsonl"

    assert meta_path.exists()
    assert not trace_path.exists()

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["case_id"] == "case_1"
    assert payload["search_mode"] == "indexed"
    assert payload["retrieval_backend"] == "chunkhound"
    assert payload["semantic_hints_used"] == 2
    assert payload["semantic_hints"] == [
        {"filename": "src/auth.py", "score": 0.91},
        {"filename": "src/login.py", "score": 0.73},
    ]
