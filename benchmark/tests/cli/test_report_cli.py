from pathlib import Path

from click.testing import CliRunner

from benchmark.cli.grid import main as grid_main
from benchmark.cli.report import main as report_main


def test_report_help_describes_text_output() -> None:
    runner = CliRunner()
    result = runner.invoke(report_main, ["--help"])

    assert result.exit_code == 0
    assert "Writes plain text / Markdown" in result.output
    assert ".json for JSON" not in result.output
    assert "Accepted formats depend on mode." in result.output


def test_report_comparison_accepts_summary_json(tmp_path: Path) -> None:
    report_path = tmp_path / "summary.json"
    report_path.write_text(
        '{"completion_rate": 1.0, "avg_quality_score": 0.5, "avg_file_recall": 0.5, '
        '"avg_file_precision": 0.5, "avg_line_coverage": 0.5, '
        '"avg_line_precision_matched": 0.5, "avg_turns": 2.0, "avg_latency_s": 1.5}\n',
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(report_main, [str(report_path)])

    assert result.exit_code == 0
    assert "Benchmark Comparison Report" in result.output
    assert tmp_path.name in result.output


def test_report_comparison_rejects_jsonl(tmp_path: Path) -> None:
    results_path = tmp_path / "sample.jsonl"
    results_path.write_text('{"case_id":"c1","completed":true,"partial":false}\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(report_main, [str(results_path)])

    assert result.exit_code != 0
    assert "Comparison mode only accepts summary.json inputs." in result.output
    assert "--failures for .jsonl" in result.output


def test_report_failures_accepts_jsonl(tmp_path: Path) -> None:
    results_path = tmp_path / "sample.jsonl"
    results_path.write_text(
        '{"case_id":"c1","repo":"example/repo","completed":false,"partial":true,'
        '"turns_used":3,"error":"timeout"}\n',
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(report_main, ["--failures", str(results_path)])

    assert result.exit_code == 0
    assert "Failure Analysis: sample.jsonl" in result.output
    assert "timeout" in result.output


def test_report_best_rejects_non_grid_json(tmp_path: Path) -> None:
    report_path = tmp_path / "summary.json"
    report_path.write_text('{"metadata": {"experiment": {"type": "run"}}}', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(report_main, ["--best", str(report_path)])

    assert result.exit_code != 0
    assert "--best only accepts a single grid summary.json file." in result.output


def test_report_best_accepts_grid_summary(tmp_path: Path) -> None:
    report_path = tmp_path / "summary.json"
    report_path.write_text(
        """
{
  "metadata": {
    "experiment": {
      "type": "grid",
      "name": "grid--curated-50--indexed--openai--avg-file-recall--20260317-154200"
    }
  },
  "grid": {
    "trials": [
      {
        "config": {
          "search_max_turns": 6,
          "search_temperature": 0.2
        },
        "paths": {
          "experiment_root": "/tmp/grid/trials/trial--turns-6--temp-0p2"
        },
        "metrics": {
          "avg_file_recall": 0.6,
          "avg_quality_score": 0.5,
          "avg_file_precision": 0.4,
          "avg_line_precision_matched": 0.45,
          "avg_turns": 4.0,
          "avg_latency_s": 3.5,
          "completion_rate": 0.8
        }
      }
    ]
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(report_main, ["--best", str(report_path)])

    assert result.exit_code == 0
    assert (
        "Best Configuration from grid--curated-50--indexed--openai--avg-file-recall--20260317-154200"
        in result.output
    )
    assert "search_max_turns" in result.output
    assert "/tmp/grid/trials/trial--turns-6--temp-0p2" in result.output


def test_report_comparison_rejects_grid_parent_report(tmp_path: Path) -> None:
    report_path = tmp_path / "summary.json"
    report_path.write_text(
        '{"metadata": {"experiment": {"type": "grid", "name": "grid-a"}}, "grid": {"trials": []}}\n',
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(report_main, [str(report_path)])

    assert result.exit_code != 0
    assert (
        "Comparison mode does not accept grid parent reports. Use --best instead." in result.output
    )


def test_grid_help_uses_current_option_names() -> None:
    runner = CliRunner()
    result = runner.invoke(grid_main, ["--help"])

    assert result.exit_code == 0
    assert "--max-turns" in result.output
    assert "--prompt-file" in result.output
    assert "--search-prompt-file" not in result.output
