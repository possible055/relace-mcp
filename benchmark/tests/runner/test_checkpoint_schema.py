import json
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmark.experiments.layout import results_path
from benchmark.experiments.runner import BenchmarkRunner
from relace_mcp.config import RelaceConfig


def test_resume_results_old_schema_fails_fast(tmp_path: Path) -> None:
    experiment_root = tmp_path / "exp-1"
    experiment_root.mkdir(parents=True)
    result_path = results_path(experiment_root)
    result_path.write_text(
        json.dumps(
            {
                "case_id": "case_1",
                "repo": "example/repo",
                "success": True,
                "returned_files_count": 0,
                "ground_truth_files_count": 0,
                "file_recall": 0.0,
                "file_precision": 0.0,
                "line_coverage": 0.0,
                "line_precision_matched": 0.0,
                "context_line_coverage": 0.0,
                "context_line_precision_matched": 0.0,
                "function_hit_rate": 0.0,
                "functions_hit": 0,
                "functions_total": 0,
                "turns_used": 0,
                "latency_ms": 123.4,
                "partial": False,
                "error": None,
                "returned_files": {},
                "raw_result": {},
                "trace_path": None,
                "hints_used": 0,
                "search_mode": "agentic",
                "retrieval_backend": None,
                "retrieval_latency_s": None,
                "reindex_action": None,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    with patch("benchmark.experiments.runner.get_repos_dir", return_value=tmp_path / "repos"):
        runner = BenchmarkRunner(
            config,
            resume=True,
            progress=False,
            artifact_root=experiment_root,
        )
        with pytest.raises(RuntimeError) as excinfo:
            runner.run_benchmark([])

    message = str(excinfo.value)
    assert "Unsupported result schema" in message
    assert str(result_path) in message
