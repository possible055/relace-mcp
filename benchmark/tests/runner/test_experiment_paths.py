import os
from datetime import UTC, datetime
from pathlib import Path

from benchmark.experiments.layout import (
    build_experiment_name,
    build_trial_name,
    collect_trace_dirs,
    events_path,
    find_latest_traces_dir,
    infer_experiment_root_from_traces,
    results_path,
    summary_path,
    traces_dir,
    trials_dir,
)


def test_experiment_paths_use_canonical_structure(tmp_path: Path) -> None:
    experiment_root = tmp_path / "experiments" / "run_locbench"

    assert results_path(experiment_root) == experiment_root / "results.jsonl"
    assert summary_path(experiment_root) == experiment_root / "summary.json"
    assert events_path(experiment_root) == experiment_root / "traces" / "events.jsonl"
    assert traces_dir(experiment_root) == experiment_root / "traces"
    assert trials_dir(experiment_root) == experiment_root / "trials"


def test_experiment_names_follow_standard_template() -> None:
    ts = datetime(2026, 3, 17, 15, 42, 0, tzinfo=UTC)

    run_name = build_experiment_name(
        "run",
        "Curated_50",
        "indexed",
        "OpenAI",
        timestamp=ts,
    )
    grid_name = build_experiment_name(
        "grid",
        "Curated_50",
        "indexed",
        "OpenAI",
        objective="avg_file_recall",
        timestamp=ts,
    )
    trial_name = build_trial_name(6, 0.2)

    assert run_name == "run--curated-50--indexed--openai--20260317-154200"
    assert grid_name == "grid--curated-50--indexed--openai--avg-file-recall--20260317-154200"
    assert trial_name == "trial--turns-6--temp-0p2"


def test_collect_trace_dirs_finds_nested_trials(tmp_path: Path) -> None:
    traces_a = tmp_path / "experiments" / "run_a" / "traces"
    traces_b = tmp_path / "experiments" / "grid_a" / "trials" / "trial-a" / "traces"
    traces_a.mkdir(parents=True)
    traces_b.mkdir(parents=True)

    trace_dirs = collect_trace_dirs(tmp_path / "experiments")

    assert trace_dirs == [traces_b, traces_a]
    assert infer_experiment_root_from_traces(traces_b) == traces_b.parent


def test_find_latest_traces_dir_uses_mtime_not_lexicographic_name(tmp_path: Path) -> None:
    older = tmp_path / "experiments" / "z-run--older" / "traces"
    newer = tmp_path / "experiments" / "a-run--newer" / "traces"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    os.utime(older, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    os.utime(newer, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000))

    assert find_latest_traces_dir(tmp_path / "experiments") == newer
