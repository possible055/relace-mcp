import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from benchmark.cli.grid import main as grid_main
from benchmark.runner.experiment_paths import experiment_report_path, experiment_results_path


def test_grid_writes_parent_summary_report_with_child_trials(tmp_path: Path) -> None:
    grid_root = tmp_path / "grid-exp"

    def fake_subprocess_run(cmd: list[str], cwd: str, env: dict[str, str], check: bool):
        output_root = Path(cmd[cmd.index("--output") + 1])
        parent_root = Path(cmd[cmd.index("--parent-experiment-root") + 1])
        report_path = experiment_report_path(output_root)
        results_path = experiment_results_path(output_root)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(
            '{"case_id":"c1","repo":"example/repo","completed":true,"partial":false}\n',
            encoding="utf-8",
        )

        turns = int(env["SEARCH_MAX_TURNS"])
        temperature = float(env["SEARCH_TEMPERATURE"])
        report_payload = {
            "metadata": {
                "experiment": {
                    "type": "trial",
                    "name": output_root.name,
                    "root": str(output_root),
                    "parent_root": str(parent_root),
                },
                "run": {
                    "cases_loaded": 1,
                },
                "search": {
                    "provider": "relace",
                },
                "retrieval": {},
                "environment": {},
                "config": {},
                "artifacts": {
                    "experiment_root": str(output_root),
                },
            },
            "completion_rate": 1.0,
            "avg_quality_score": 0.4 + temperature,
            "avg_file_recall": 0.5 + (0.01 * turns),
            "avg_file_precision": 0.5,
            "avg_line_coverage": 0.5,
            "avg_line_precision_matched": 0.5,
            "avg_turns": float(turns),
            "avg_latency_s": 1.5,
        }
        report_path.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    runner = CliRunner()
    with (
        patch("benchmark.cli.grid.initialize_runtime_from_env", lambda: None),
        patch("benchmark.cli.grid.subprocess.run", side_effect=fake_subprocess_run),
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

    parent_report = experiment_report_path(grid_root)
    assert parent_report.exists()
    assert not (grid_root / "results" / "results.jsonl").exists()
    assert not (grid_root / "reports" / "grid.report.json").exists()

    payload = json.loads(parent_report.read_text(encoding="utf-8"))
    assert payload["metadata"]["experiment"]["type"] == "grid"
    assert payload["metadata"]["experiment"]["root"] == str(grid_root)
    assert payload["grid"]["objective"] == "avg_file_recall"
    assert payload["grid"]["trial_count"] == 4
    assert len(payload["grid"]["trials"]) == 4
    assert payload["grid"]["best_trial"]["config"]["search_max_turns"] == 6
