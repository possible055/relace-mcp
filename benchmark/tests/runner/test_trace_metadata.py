import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from benchmark.analysis.trace_artifacts import TRACE_ARTIFACT_SCHEMA_VERSION
from benchmark.runner.executor import BenchmarkRunner
from benchmark.runner.results import BenchmarkResult, BenchmarkSummary
from benchmark.runner.trace_recorder import BenchmarkTraceRecorder
from benchmark.schemas import DatasetCase
from relace_mcp.config import RelaceConfig


def test_execute_search_writes_trace_meta_without_turns_log(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    experiment_root = tmp_path / "experiment"

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    runner = BenchmarkRunner(config, progress=False, trace=True, search_mode="indexed")
    runner.trace_recorder = BenchmarkTraceRecorder(
        enabled=True,
        experiment_root=experiment_root,
        run_id="run_1",
        search_mode="indexed",
    )
    runner.trace_recorder.start_run()

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

    try:
        with (
            patch("benchmark.runner.executor.SearchLLMClient", return_value=MagicMock()),
            patch("benchmark.runner.executor.get_lsp_languages", return_value=frozenset()),
            patch("benchmark.runner.preflight.check_retrieval_backend", return_value={"ok": True}),
            patch("relace_mcp.clients.RelaceRepoClient", return_value=MagicMock()),
            patch(
                "relace_mcp.search.agentic_retrieval_logic",
                new=fake_agentic_retrieval_logic,
            ),
        ):
            result = runner._execute_search(case, repo_path)
    finally:
        runner.trace_recorder.finish_run()

    traces_dir = runner.trace_recorder.traces_dir
    assert traces_dir is not None
    meta_path = traces_dir / "case_1.meta.json"
    trace_path = traces_dir / "case_1.jsonl"

    assert meta_path.exists()
    assert not trace_path.exists()
    assert result.trace_meta_path == str(meta_path)
    assert result.trace_path is None
    assert result.artifact_status == {
        "trace_jsonl": "missing",
        "trace_meta": "written",
    }

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == TRACE_ARTIFACT_SCHEMA_VERSION
    assert payload["case_id"] == "case_1"
    assert payload["search_mode"] == "indexed"
    assert payload["retrieval_backend"] == "chunkhound"
    assert payload["semantic_hints_used"] == 2
    assert payload["semantic_hints"] == [
        {"filename": "src/auth.py", "score": 0.91},
        {"filename": "src/login.py", "score": 0.73},
    ]


def test_execute_search_emits_search_complete_with_retrieval_fields(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    experiment_root = tmp_path / "experiment"

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    runner = BenchmarkRunner(config, progress=False, trace=True, search_mode="indexed")
    runner.trace_recorder = BenchmarkTraceRecorder(
        enabled=True,
        experiment_root=experiment_root,
        run_id="run_1",
        search_mode="indexed",
    )
    runner.trace_recorder.start_run()

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
            "turns_used": 2,
            "retrieval_backend": "chunkhound",
            "retrieval_latency_s": 0.123,
            "hint_policy": "prefer-stale",
            "hints_index_freshness": "stale",
            "background_refresh_scheduled": True,
            "reindex_action": "scheduled_background_refresh",
            "semantic_hints_used": 2,
            "semantic_hints": [
                {"filename": "src/auth.py", "score": 0.91},
                {"filename": "src/login.py", "score": 0.73},
            ],
        }

    try:
        with (
            patch("benchmark.runner.executor.SearchLLMClient", return_value=MagicMock()),
            patch("benchmark.runner.executor.get_lsp_languages", return_value=frozenset()),
            patch("benchmark.runner.preflight.check_retrieval_backend", return_value={"ok": True}),
            patch("relace_mcp.clients.RelaceRepoClient", return_value=MagicMock()),
            patch(
                "relace_mcp.search.agentic_retrieval_logic",
                new=fake_agentic_retrieval_logic,
            ),
        ):
            runner._execute_search(case, repo_path)
    finally:
        runner.trace_recorder.finish_run()

    events_path = runner.trace_recorder.events_path
    assert events_path is not None
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    search_complete = [event for event in events if event.get("kind") == "search_complete"]
    assert len(search_complete) == 1
    payload = search_complete[0]
    assert payload["schema_version"] == TRACE_ARTIFACT_SCHEMA_VERSION
    assert payload["retrieval_backend"] == "chunkhound"
    assert payload["semantic_hints_used"] == 2
    assert payload["hint_policy"] == "prefer-stale"
    assert payload["hints_index_freshness"] == "stale"
    assert payload["background_refresh_scheduled"] is True
    assert payload["reindex_action"] == "scheduled_background_refresh"
    assert payload["total_latency_ms"] >= 0


def test_summary_save_persists_trace_pointers_without_raw_result(tmp_path: Path) -> None:
    result = BenchmarkResult(
        case_id="case_1",
        repo="example/repo",
        completed=True,
        returned_files_count=1,
        ground_truth_files_count=1,
        file_recall=1.0,
        file_precision=1.0,
        line_coverage=1.0,
        line_precision_matched=1.0,
        context_line_coverage=1.0,
        context_line_precision_matched=1.0,
        function_hit_rate=1.0,
        functions_hit=1,
        functions_total=1,
        turns_used=2,
        latency_s=0.5,
        trace_path="/tmp/case_1.jsonl",
        trace_meta_path="/tmp/case_1.meta.json",
        artifact_status={"trace_jsonl": "written", "trace_meta": "written"},
    )
    summary = BenchmarkSummary(
        metadata={"artifacts": {}}, total_cases=1, stats={}, results=[result]
    )

    output_path = tmp_path / "run.jsonl"
    summary.save(output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8").strip())
    assert "raw_result" not in payload
    assert payload["trace_path"] == "/tmp/case_1.jsonl"
    assert payload["trace_meta_path"] == "/tmp/case_1.meta.json"
    assert payload["artifact_status"] == {
        "trace_jsonl": "written",
        "trace_meta": "written",
    }
