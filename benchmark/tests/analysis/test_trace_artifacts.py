import json
from pathlib import Path

from benchmark.analysis.trace_artifacts import (
    TRACE_ARTIFACT_SCHEMA_VERSION,
    _read_event_lines,
    collect_trace_artifacts,
    load_trace_meta,
    load_trace_turns,
    validate_trace_run,
)
from benchmark.runner.executor import BenchmarkRunner
from relace_mcp.config import RelaceConfig


def test_collect_trace_artifacts_includes_meta_only_case(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir()

    (traces_dir / "case_1.meta.json").write_text("{}", encoding="utf-8")
    (traces_dir / "case_2.jsonl").write_text('{"turn": 1}\n', encoding="utf-8")
    (traces_dir / "case_2.meta.json").write_text("{}", encoding="utf-8")

    artifacts = collect_trace_artifacts(traces_dir)

    assert [artifact.case_id for artifact in artifacts] == ["case_1", "case_2"]
    assert artifacts[0].trace_path is None
    assert artifacts[0].meta_path == traces_dir / "case_1.meta.json"
    assert artifacts[1].trace_path == traces_dir / "case_2.jsonl"


def test_validate_trace_run_detects_meta_event_mismatch(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces" / "run_1"
    traces_dir.mkdir(parents=True)
    events_path = tmp_path / "events" / "run_1.jsonl"
    events_path.parent.mkdir(parents=True)

    (traces_dir / "case_1.jsonl").write_text(
        json.dumps({"turn": 1, "tool_calls_raw": [], "tool_results": []}) + "\n",
        encoding="utf-8",
    )
    (traces_dir / "case_1.meta.json").write_text(
        json.dumps(
            {
                "schema_version": TRACE_ARTIFACT_SCHEMA_VERSION,
                "case_id": "case_1",
                "repo": "example/repo",
                "search_mode": "indexed",
                "retrieval_backend": "chunkhound",
                "hint_policy": "prefer-stale",
                "hints_index_freshness": "fresh",
                "background_refresh_scheduled": False,
                "reindex_action": None,
                "semantic_hints_used": 2,
                "semantic_hints": [
                    {"filename": "src/a.py", "score": 0.9},
                    {"filename": "src/b.py", "score": 0.8},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text(
        json.dumps(
            {
                "schema_version": TRACE_ARTIFACT_SCHEMA_VERSION,
                "kind": "search_complete",
                "case_id": "case_1",
                "repo": "example/repo",
                "search_mode": "indexed",
                "turns_used": 1,
                "partial": False,
                "files_found": 0,
                "total_latency_ms": 100.0,
                "retrieval_backend": "chunkhound",
                "semantic_hints_used": 1,
                "hint_policy": "prefer-stale",
                "hints_index_freshness": "fresh",
                "background_refresh_scheduled": False,
                "reindex_action": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = validate_trace_run(traces_dir, events_path=events_path)

    assert summary.total_cases == 1
    assert summary.invalid_cases == 1
    assert summary.total_errors >= 1
    assert any(
        "semantic_hints_used mismatch between meta and events" in error
        for error in summary.results[0].errors
    )


def test_run_benchmark_metadata_includes_trace_artifacts(tmp_path: Path) -> None:
    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    runner = BenchmarkRunner(config, progress=False, trace=True)
    runner.repos_dir = tmp_path / "repos"
    runner.repos_dir.mkdir()

    summary = runner.run_benchmark([])

    artifacts = summary.metadata["artifacts"]
    experiment = summary.metadata["experiment"]
    assert artifacts["trace_enabled"] is True
    assert artifacts["schema_version"] == TRACE_ARTIFACT_SCHEMA_VERSION
    assert artifacts["run_id"]
    assert artifacts["experiment_root"].endswith(f"/experiments/{artifacts['run_id']}")
    assert artifacts["traces_dir"].endswith(f"/experiments/{artifacts['run_id']}/traces")
    assert artifacts["events_path"].endswith(
        f"/experiments/{artifacts['run_id']}/events/events.jsonl"
    )
    assert experiment["type"] == "run"
    assert experiment["root"] == artifacts["experiment_root"]
    assert experiment["name"] == artifacts["experiment_root"].split("/")[-1]
    assert experiment["parent_root"] is None


def test_run_benchmark_metadata_supports_trial_experiment_type(tmp_path: Path) -> None:
    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    runner = BenchmarkRunner(
        config, progress=False, trace=False, artifact_root=tmp_path / "trial-exp"
    )
    runner.repos_dir = tmp_path / "repos"
    runner.repos_dir.mkdir()

    summary = runner.run_benchmark(
        [],
        run_config={
            "experiment_type": "trial",
            "parent_experiment_root": str(tmp_path / "grid-exp"),
        },
    )

    experiment = summary.metadata["experiment"]
    assert experiment["type"] == "trial"
    assert experiment["root"] == str(tmp_path / "trial-exp")
    assert experiment["name"] == "trial-exp"
    assert experiment["parent_root"] == str(tmp_path / "grid-exp")


def test_load_trace_meta_includes_json_error_details(tmp_path: Path) -> None:
    meta_path = tmp_path / "case_1.meta.json"
    meta_path.write_text("{\n", encoding="utf-8")

    payload, errors = load_trace_meta(meta_path)

    assert payload == {}
    assert len(errors) == 1
    assert errors[0].startswith(f"Invalid JSON in trace metadata: {meta_path}: ")


def test_load_trace_meta_includes_os_error_details(tmp_path: Path, monkeypatch) -> None:
    meta_path = tmp_path / "case_1.meta.json"
    meta_path.write_text("{}\n", encoding="utf-8")

    def _raise_os_error(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _raise_os_error)

    payload, errors = load_trace_meta(meta_path)

    assert payload == {}
    assert errors == [f"Unable to read trace metadata: {meta_path}: permission denied"]


def test_load_trace_turns_includes_json_error_details(tmp_path: Path) -> None:
    trace_path = tmp_path / "case_1.jsonl"
    trace_path.write_text("{\n", encoding="utf-8")

    turns, errors = load_trace_turns(trace_path)

    assert turns == []
    assert len(errors) == 1
    assert errors[0].startswith(f"Invalid JSON in {trace_path}:1: ")


def test_read_event_lines_includes_json_error_details(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("{\n", encoding="utf-8")

    events, errors = _read_event_lines(events_path)

    assert events == []
    assert len(errors) == 1
    assert errors[0].startswith(f"Invalid JSON in {events_path}:1: ")
