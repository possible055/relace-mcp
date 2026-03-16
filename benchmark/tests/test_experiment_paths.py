from pathlib import Path

from benchmark.experiment_paths import (
    collect_trace_dirs,
    experiment_events_path,
    experiment_report_path,
    experiment_results_path,
    experiment_traces_dir,
    grid_runs_dir,
    infer_experiment_root_from_traces,
)


def test_experiment_paths_use_purpose_named_structure(tmp_path: Path) -> None:
    experiment_root = tmp_path / "experiments" / "run_locbench"

    assert experiment_results_path(experiment_root) == experiment_root / "results" / "results.jsonl"
    assert (
        experiment_report_path(experiment_root)
        == experiment_root / "reports" / "summary.report.json"
    )
    assert experiment_events_path(experiment_root) == experiment_root / "events" / "events.jsonl"
    assert experiment_traces_dir(experiment_root) == experiment_root / "traces"
    assert grid_runs_dir(experiment_root) == experiment_root / "runs"


def test_collect_trace_dirs_finds_nested_grid_runs(tmp_path: Path) -> None:
    traces_a = tmp_path / "experiments" / "run_a" / "traces"
    traces_b = tmp_path / "experiments" / "grid_a" / "runs" / "t4__temp0" / "traces"
    traces_a.mkdir(parents=True)
    traces_b.mkdir(parents=True)

    trace_dirs = collect_trace_dirs(tmp_path / "experiments")

    assert trace_dirs == [traces_b, traces_a]
    assert infer_experiment_root_from_traces(traces_b) == traces_b.parent
