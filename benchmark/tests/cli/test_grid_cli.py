import json
import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from benchmark.cli.grid import main as grid_main
from benchmark.experiments.layout import (
    experiment_report_path,
    experiment_results_path,
    summary_path,
)
from relace_mcp.config import RelaceConfig


class _FakeSummary:
    def __init__(self, experiment_root: Path) -> None:
        turns = int(os.environ["SEARCH_MAX_TURNS"])
        temperature = float(os.environ["SEARCH_TEMPERATURE"])
        self.stats = {
            "completion_rate": 1.0,
            "avg_quality_score": 0.4 + temperature,
            "avg_file_recall": 0.5 + (0.01 * turns),
            "avg_file_precision": 0.5,
            "avg_line_coverage": 0.5,
            "avg_line_precision_matched": 0.5,
            "avg_turns": float(turns),
            "avg_latency_s": 1.5,
        }
        self.total_cases = 1
        self.experiment_root = experiment_root

    def save(self, results_path: Path, report_path: Path | None = None) -> None:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(
            '{"case_id":"c1","repo":"example/repo","completed":true,"partial":false}\n',
            encoding="utf-8",
        )
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps({"stats": self.stats}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        (self.experiment_root / "manifest.json").write_text("{}\n", encoding="utf-8")
        (self.experiment_root / "state.json").write_text("{}\n", encoding="utf-8")


class _FakeRunner:
    def __init__(self, *_args, artifact_root: Path | None = None, **_kwargs) -> None:
        self.artifact_root = artifact_root or Path(".")

    def run_benchmark(self, _cases, *, run_config=None):
        return _FakeSummary(self.artifact_root)


def test_grid_writes_parent_summary_report_with_child_trials(tmp_path: Path) -> None:
    grid_root = tmp_path / "grid-exp"

    runner = CliRunner()
    with (
        patch("benchmark.cli.grid.initialize_runtime_from_env", lambda: None),
        patch("benchmark.cli.grid.load_dataset", return_value=[object()]),
        patch(
            "benchmark.cli.grid._load_benchmark_config",
            return_value=RelaceConfig(api_key="rlc-test", base_dir=None),
        ),
        patch("benchmark.cli.grid.BenchmarkRunner", _FakeRunner),
    ):
        result = runner.invoke(
            grid_main,
            [
                "--dataset",
                "artifacts/data/processed/curated_50.jsonl",
                "--max-turns",
                "4",
                "--temperatures",
                "0.2",
                "--max-turns",
                "6",
                "--temperatures",
                "0.4",
                "-o",
                str(grid_root),
            ],
        )

    assert result.exit_code == 0

    parent_report = summary_path(grid_root)
    assert parent_report.exists()
    assert not experiment_results_path(grid_root).exists()
    assert not experiment_report_path(grid_root).with_name("grid.report.json").exists()

    payload = json.loads(parent_report.read_text(encoding="utf-8"))
    assert payload["metadata"]["experiment"]["type"] == "grid"
    assert payload["metadata"]["experiment"]["root"] == str(grid_root)
    assert payload["stats"]["trial_count"] == 4
    assert len(payload["trials"]) == 4
    assert payload["best_trial"]["config"]["search_max_turns"] == 6
