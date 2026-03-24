import importlib.util
import json
import logging
from pathlib import Path

_DISCOVERY_PATH = Path(__file__).resolve().parents[2] / "viewer" / "discovery.py"
_DISCOVERY_SPEC = importlib.util.spec_from_file_location("test_discovery_module", _DISCOVERY_PATH)
assert _DISCOVERY_SPEC is not None
assert _DISCOVERY_SPEC.loader is not None
_DISCOVERY_MODULE = importlib.util.module_from_spec(_DISCOVERY_SPEC)
_DISCOVERY_SPEC.loader.exec_module(_DISCOVERY_MODULE)
list_experiments = _DISCOVERY_MODULE.list_experiments


def test_list_experiments_logs_and_skips_malformed_reports(
    tmp_path: Path,
    caplog,
) -> None:
    valid_root = tmp_path / "valid-run"
    invalid_root = tmp_path / "invalid-run"
    (valid_root / "reports").mkdir(parents=True)
    (invalid_root / "reports").mkdir(parents=True)

    (valid_root / "reports" / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {"name": "valid-run", "type": "run"},
                    "search": {"provider": "openai", "model": "gpt-5-mini"},
                    "run": {"search_mode": "agentic"},
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (invalid_root / "reports" / "summary.report.json").write_text("{\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        summaries = list_experiments(tmp_path)

    assert [summary["name"] for summary in summaries] == ["valid-run"]
    assert any("Skipping malformed report" in record.message for record in caplog.records)
