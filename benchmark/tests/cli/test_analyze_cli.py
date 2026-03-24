import os
from pathlib import Path

from click.testing import CliRunner

from benchmark.cli.analyze import main as analyze_main


def test_analyze_defaults_to_most_recent_results_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiments_dir = tmp_path / "experiments"
    older = experiments_dir / "z-run--older" / "results" / "results.jsonl"
    newer = experiments_dir / "a-run--newer" / "results" / "results.jsonl"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)

    older.write_text(
        '{"case_id":"older","file_recall":0.1,"file_precision":0.1,'
        '"line_coverage":0.1,"line_precision_matched":0.1,"turns_used":1,"latency_s":1.0}\n',
        encoding="utf-8",
    )
    newer.write_text(
        '{"case_id":"newer","file_recall":0.9,"file_precision":0.9,'
        '"line_coverage":0.9,"line_precision_matched":0.9,"turns_used":1,"latency_s":1.0}\n',
        encoding="utf-8",
    )

    os.utime(older, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    os.utime(newer, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000))

    monkeypatch.setattr("benchmark.cli.analyze.get_experiments_dir", lambda: experiments_dir)

    runner = CliRunner()
    result = runner.invoke(analyze_main, [])

    assert result.exit_code == 0
    assert f"Analyzing 1 benchmark results from: {newer}" in result.output
    assert "newer" in result.output


def test_analyze_raises_click_exception_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jsonl"

    runner = CliRunner()
    result = runner.invoke(analyze_main, [str(missing_path)])

    assert result.exit_code == 1
    assert f"Error: File not found: {missing_path}" in result.output


def test_analyze_raises_click_exception_for_empty_results(tmp_path: Path) -> None:
    results_path = tmp_path / "results.json"
    results_path.write_text("[]\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(analyze_main, [str(results_path)])

    assert result.exit_code == 1
    assert "Error: No results found." in result.output
