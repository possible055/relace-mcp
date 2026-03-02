import json
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmark.runner.executor import BenchmarkRunner
from relace_mcp.config import RelaceConfig


def test_resume_checkpoint_old_schema_fails_fast(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    checkpoint_path.write_text(
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

    with patch("benchmark.runner.executor.get_repos_dir", return_value=tmp_path / "repos"):
        runner = BenchmarkRunner(
            config,
            resume=True,
            checkpoint_path=checkpoint_path,
            progress=False,
        )
        with pytest.raises(RuntimeError) as excinfo:
            runner.run_benchmark([])

    message = str(excinfo.value)
    assert "Unsupported checkpoint schema" in message
    assert str(checkpoint_path) in message
