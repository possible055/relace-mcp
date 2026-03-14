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


def test_report_comparison_accepts_report_json(tmp_path: Path) -> None:
    report_path = tmp_path / "sample.report.json"
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
    assert "sample.report" in result.output


def test_report_comparison_rejects_jsonl(tmp_path: Path) -> None:
    results_path = tmp_path / "sample.jsonl"
    results_path.write_text('{"case_id":"c1","completed":true,"partial":false}\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(report_main, [str(results_path)])

    assert result.exit_code != 0
    assert "Comparison mode only accepts .report.json inputs." in result.output
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
    report_path = tmp_path / "sample.report.json"
    report_path.write_text("{}", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(report_main, ["--best", str(report_path)])

    assert result.exit_code != 0
    assert "--best only accepts a single .grid.json file." in result.output


def test_grid_help_uses_current_option_names() -> None:
    runner = CliRunner()
    result = runner.invoke(grid_main, ["--help"])

    assert result.exit_code == 0
    assert "--max-turns" in result.output
    assert "--prompt-file" in result.output
    assert "--search-prompt-file" not in result.output
