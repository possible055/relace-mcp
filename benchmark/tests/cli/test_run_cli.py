import sys
import types
from collections.abc import Generator
from datetime import UTC
from pathlib import Path

import pytest
from click.testing import CliRunner

from benchmark.cli.run import main as run_main
from relace_mcp.config import settings as _settings


class _FakeSummary:
    def __init__(self) -> None:
        self.total_cases = 0
        self.stats = {
            "completion_rate": 0.0,
            "avg_quality_score": 0.0,
            "avg_returned_files": 0.0,
            "avg_ground_truth_files": 0.0,
            "avg_file_recall": 0.0,
            "avg_file_precision": 0.0,
            "avg_line_coverage": 0.0,
            "avg_line_precision_matched": 0.0,
            "avg_context_line_coverage": 0.0,
            "avg_context_line_precision_matched": 0.0,
            "function_cases": 0.0,
            "avg_function_hit_rate": 0.0,
            "avg_turns": 0.0,
            "avg_latency_s": 0.0,
        }

    def save(self, results_path: Path, report_path: Path | None = None) -> None:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text("", encoding="utf-8")
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("{}", encoding="utf-8")


class _FakeRunner:
    def __init__(self, *_args, **_kwargs) -> None:
        self.trace_recorder = None

    def run_benchmark(self, _cases, *, run_config=None):
        return _FakeSummary()


@pytest.fixture(autouse=True)
def _restore_settings() -> Generator[None, None, None]:
    snapshot = {
        "SEARCH_MAX_TURNS": _settings.SEARCH_MAX_TURNS,
        "SEARCH_TEMPERATURE": _settings.SEARCH_TEMPERATURE,
    }
    yield
    for key, value in snapshot.items():
        setattr(_settings, key, value)


def test_run_uses_utc_timestamp_for_default_experiment_name(tmp_path: Path, monkeypatch) -> None:
    experiments_dir = tmp_path / "experiments"
    captured: dict[str, object] = {}

    def fake_build_experiment_name(*args, **kwargs):
        captured["timestamp"] = kwargs["timestamp"]
        return "run--captured"

    monkeypatch.setattr("benchmark.cli.run.initialize_runtime_from_env", lambda: None)
    monkeypatch.setattr("benchmark.cli.run.reload_runtime_from_env", lambda: None)
    monkeypatch.setattr("benchmark.cli.run.load_dataset", lambda **_kwargs: [])
    monkeypatch.setattr("benchmark.cli.run._load_benchmark_config", lambda: object())
    monkeypatch.setattr("benchmark.cli.run.get_benchmark_dir", lambda: tmp_path)
    monkeypatch.setattr("benchmark.cli.run.get_experiments_dir", lambda: experiments_dir)
    monkeypatch.setattr("benchmark.cli.run.build_experiment_name", fake_build_experiment_name)
    fake_executor = types.ModuleType("benchmark.runner.executor")
    fake_executor.BenchmarkRunner = _FakeRunner
    monkeypatch.setitem(sys.modules, "benchmark.runner.executor", fake_executor)

    runner = CliRunner()
    result = runner.invoke(run_main, [])

    assert result.exit_code == 0
    timestamp = captured["timestamp"]
    assert getattr(timestamp, "tzinfo", None) is UTC


def test_run_cli_reloads_settings_after_cli_overrides(tmp_path: Path, monkeypatch) -> None:
    experiments_dir = tmp_path / "experiments"

    def fake_initialize() -> None:
        monkeypatch.setenv("SEARCH_MAX_TURNS", "5")
        monkeypatch.setenv("SEARCH_TEMPERATURE", "0.9")

    monkeypatch.setattr("benchmark.cli.run.initialize_runtime_from_env", fake_initialize)
    monkeypatch.setattr("benchmark.cli.run.load_dataset", lambda **_kwargs: [])
    monkeypatch.setattr("benchmark.cli.run._load_benchmark_config", lambda: object())
    monkeypatch.setattr("benchmark.cli.run.get_benchmark_dir", lambda: tmp_path)
    monkeypatch.setattr("benchmark.cli.run.get_experiments_dir", lambda: experiments_dir)
    fake_executor = types.ModuleType("benchmark.runner.executor")
    fake_executor.BenchmarkRunner = _FakeRunner
    monkeypatch.setitem(sys.modules, "benchmark.runner.executor", fake_executor)

    runner = CliRunner()
    result = runner.invoke(run_main, ["--max-turns", "8", "--temperature", "0.2"])

    assert result.exit_code == 0
    assert _settings.SEARCH_MAX_TURNS == 8
    assert _settings.SEARCH_TEMPERATURE == 0.2
