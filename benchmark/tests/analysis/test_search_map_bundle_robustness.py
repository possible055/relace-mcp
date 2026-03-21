import json
from pathlib import Path

from benchmark.analysis.search_map_bundle import _load_json, _load_results_by_case
from benchmark.viewer.discovery import list_experiments


class TestLoadJsonCorruptFile:
    def test_returns_none_on_truncated_json(self, tmp_path: Path) -> None:
        corrupt = tmp_path / "bad.json"
        corrupt.write_text('{"kind": "search_map_bundle", "cases": [', encoding="utf-8")

        result = _load_json(corrupt)

        assert result is None

    def test_returns_none_on_nonexistent_path(self) -> None:
        result = _load_json(Path("/nonexistent/path.json"))
        assert result is None

    def test_returns_valid_data_on_good_file(self, tmp_path: Path) -> None:
        good = tmp_path / "ok.json"
        good.write_text('{"key": "value"}', encoding="utf-8")

        result = _load_json(good)

        assert result == {"key": "value"}


class TestLoadResultsByCaseCorruptLines:
    def test_skips_corrupt_lines_keeps_good(self, tmp_path: Path) -> None:
        results_path = tmp_path / "results.jsonl"
        lines = [
            json.dumps({"case_id": "case_1", "completed": True}),
            "{truncated",
            json.dumps({"case_id": "case_2", "completed": True}),
            "",
            "not json at all",
            json.dumps({"case_id": "case_3", "completed": False}),
        ]
        results_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = _load_results_by_case(results_path)

        assert set(result.keys()) == {"case_1", "case_2", "case_3"}
        assert result["case_1"]["completed"] is True
        assert result["case_3"]["completed"] is False


class TestListExperimentsCorruptReport:
    def test_skips_corrupt_report_returns_valid(self, tmp_path: Path) -> None:
        good_root = tmp_path / "good-run"
        bad_root = tmp_path / "bad-run"

        good_reports = good_root / "reports"
        good_reports.mkdir(parents=True)
        (good_reports / "summary.report.json").write_text(
            json.dumps(
                {
                    "metadata": {
                        "experiment": {"type": "run", "name": "good-run"},
                        "search": {"provider": "openai", "model": "gpt-5"},
                        "run": {"search_mode": "agentic"},
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        bad_reports = bad_root / "reports"
        bad_reports.mkdir(parents=True)
        (bad_reports / "summary.report.json").write_text(
            '{"metadata": {truncated',
            encoding="utf-8",
        )

        experiments = list_experiments(tmp_path)

        assert len(experiments) == 1
        assert experiments[0]["name"] == "good-run"
