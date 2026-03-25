"""Tests for ExperimentIndex."""

import json
from datetime import UTC, datetime
from pathlib import Path

from benchmark.experiments.index import ExperimentIndex
from benchmark.experiments.models import ExperimentManifest, ExperimentState
from benchmark.experiments.store import ExperimentStore


def _write_experiment(root: Path, *, experiment_id: str, kind: str = "run") -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest = ExperimentManifest(
        experiment_id=experiment_id,
        kind=kind,
        name=experiment_id,
        experiment_root=root,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        dataset={"name": "locbench", "case_count": 2, "dataset_path": "/tmp/locbench.jsonl"},
        search={"provider": "openai", "model": "gpt-4.1"},
        environment={"python_version": "3.12"},
    )
    manifest.save()
    ExperimentState(
        status="completed",
        total_cases=2,
        completed_cases=2,
        failed_cases=0,
    ).save(root)
    (root / "summary.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {"type": kind, "name": experiment_id, "root": str(root)}
                },
                "manifest": manifest.to_dict(),
                "state": {
                    "status": "completed",
                    "total_cases": 2,
                    "completed_cases": 2,
                    "failed_cases": 0,
                },
                "stats": {
                    "completion_rate": 1.0,
                    "avg_file_recall": 0.75,
                    "avg_file_precision": 0.5,
                    "avg_line_coverage": 0.6,
                    "avg_function_hit_rate": 0.5,
                    "avg_turns": 3.0,
                    "avg_latency_s": 1.2,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "results.jsonl").write_text(
        json.dumps(
            {
                "case_id": "case_001",
                "repo": "example/repo",
                "completed": True,
                "returned_files_count": 1,
                "ground_truth_files_count": 1,
                "file_recall": 1.0,
                "file_precision": 0.5,
                "line_coverage": 0.6,
                "line_precision_matched": 0.6,
                "context_line_coverage": 0.6,
                "context_line_precision_matched": 0.6,
                "function_hit_rate": 0.5,
                "functions_hit": 1,
                "functions_total": 2,
                "turns_used": 3,
                "latency_s": 1.2,
                "partial": False,
                "returned_files": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_rebuild_and_get_experiment(tmp_path: Path) -> None:
    experiments_dir = tmp_path / "experiments"
    _write_experiment(experiments_dir / "run-a", experiment_id="run-a")
    store = ExperimentStore(experiments_dir)
    index = ExperimentIndex(tmp_path / "index.sqlite3")

    try:
        count = index.rebuild(store)
        assert count == 1

        experiment = index.get_experiment("run-a")
        assert experiment is not None
        assert experiment.experiment_id == "run-a"
        assert experiment.kind == "run"
        assert experiment.avg_file_recall == 0.75
    finally:
        index.close()


def test_list_experiments_filters_kind_and_dataset(tmp_path: Path) -> None:
    experiments_dir = tmp_path / "experiments"
    _write_experiment(experiments_dir / "run-a", experiment_id="run-a", kind="run")
    _write_experiment(experiments_dir / "grid-a", experiment_id="grid-a", kind="grid")
    store = ExperimentStore(experiments_dir)
    index = ExperimentIndex(tmp_path / "index.sqlite3")

    try:
        index.rebuild(store)
        runs = index.list_experiments(kinds=["run"])
        assert [item.experiment_id for item in runs] == ["run-a"]
        assert index.count_experiments(kinds=["grid"]) == 1
    finally:
        index.close()


def test_list_cases_and_invalidate(tmp_path: Path) -> None:
    experiments_dir = tmp_path / "experiments"
    _write_experiment(experiments_dir / "run-a", experiment_id="run-a")
    store = ExperimentStore(experiments_dir)
    index = ExperimentIndex(tmp_path / "index.sqlite3")

    try:
        index.rebuild(store)
        cases = index.list_cases("run-a")
        assert len(cases) == 1
        assert cases[0].case_id == "case_001"

        index.invalidate("run-a")
        assert index.get_experiment("run-a") is None
        assert index.list_cases("run-a") == []
    finally:
        index.close()
