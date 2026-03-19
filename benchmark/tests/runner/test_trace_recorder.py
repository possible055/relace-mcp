import json
from pathlib import Path

from benchmark.runner.results import BenchmarkResult
from benchmark.runner.trace_recorder import BenchmarkTraceRecorder


def test_trace_recorder_start_run_sets_artifact_paths(tmp_path: Path) -> None:
    experiment_root = tmp_path / "experiment"
    recorder = BenchmarkTraceRecorder(
        enabled=True,
        experiment_root=experiment_root,
        run_id="run_1",
        search_mode="indexed",
    )

    recorder.start_run()
    try:
        metadata = recorder.artifact_metadata()
    finally:
        recorder.finish_run()

    assert recorder.traces_dir == experiment_root / "traces"
    assert recorder.events_path == experiment_root / "events" / "events.jsonl"
    assert metadata["trace_enabled"] is True
    assert metadata["run_id"] == "run_1"
    assert metadata["experiment_root"] == str(experiment_root)
    assert metadata["traces_dir"] == str(experiment_root / "traces")
    assert metadata["events_path"] == str(experiment_root / "events" / "events.jsonl")


def test_trace_recorder_writes_trace_meta_and_events(tmp_path: Path) -> None:
    experiment_root = tmp_path / "experiment"
    recorder = BenchmarkTraceRecorder(
        enabled=True,
        experiment_root=experiment_root,
        run_id="run_1",
        search_mode="indexed",
    )
    turns_log = [
        {
            "turn": 1,
            "llm_latency_ms": 12.5,
            "llm_response": {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                }
            },
            "tool_results": [
                {
                    "id": "call_1",
                    "name": "view_file",
                    "latency_ms": 3.2,
                    "success": True,
                }
            ],
        }
    ]
    result = {
        "turns_used": 1,
        "retrieval_backend": "chunkhound",
        "semantic_hints_used": 2,
        "semantic_hints": [
            {"filename": "src/auth.py", "score": 0.9},
            {"filename": "src/login.py", "score": 0.8},
        ],
        "hint_policy": "prefer-stale",
        "hints_index_freshness": "fresh",
        "background_refresh_scheduled": False,
        "reindex_action": None,
    }
    benchmark_result = BenchmarkResult(
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
        turns_used=1,
        latency_s=0.4,
        hints_used=2,
        search_mode="indexed",
        retrieval_backend="chunkhound",
    )

    recorder.start_run()
    try:
        recorder.write_search_start(
            case_id="case_1",
            repo="example/repo",
            query="find auth logic",
        )
        trace_write = recorder.write_case_trace(case_id="case_1", turns_log=turns_log)
        meta_write = recorder.write_case_meta(
            case_id="case_1",
            repo="example/repo",
            query="find auth logic",
            result=result,
        )
        recorder.write_case_events(
            case_id="case_1",
            repo="example/repo",
            benchmark_result=benchmark_result,
            result=result,
            turns_log=turns_log,
        )
    finally:
        recorder.finish_run()

    assert trace_write.state == "written"
    assert meta_write.state == "written"
    assert trace_write.path is not None
    assert meta_write.path is not None

    trace_payload = Path(trace_write.path).read_text(encoding="utf-8").splitlines()
    assert len(trace_payload) == 1

    meta_payload = json.loads(Path(meta_write.path).read_text(encoding="utf-8"))
    assert meta_payload["case_id"] == "case_1"
    assert meta_payload["query"] == "find auth logic"
    assert meta_payload["semantic_hints_used"] == 2

    assert recorder.events_path is not None
    events = [
        json.loads(line) for line in recorder.events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["kind"] for event in events] == [
        "search_start",
        "search_turn",
        "tool_call",
        "search_complete",
    ]
