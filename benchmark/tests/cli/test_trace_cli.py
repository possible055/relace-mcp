import json
from pathlib import Path

from click.testing import CliRunner

from benchmark.cli.trace import main as trace_main


def test_trace_search_map_json_out_includes_semantic_hints(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir()

    trace_path = traces_dir / "case_1.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "turn": 1,
                "tool_calls_raw": [],
                "tool_results": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trace_path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "case_id": "case_1",
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 2,
                "semantic_hints": [
                    {"filename": "/repo/src/main.py", "score": 0.9},
                    {"filename": "./src/util.py", "score": 0.7},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        trace_main,
        [str(traces_dir), "--search-map", "--json-out", "-o", "search_map.json"],
    )

    assert result.exit_code == 0
    output_path = tmp_path / "reports" / "search_map.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "search_map_bundle"
    assert payload["summary"]["cases_with_semantic_hints"] == 1
    assert payload["summary"]["avg_semantic_hints_per_case"] == 2.0
    assert payload["cases"][0]["semantic_hints"] == [
        {"filename": "src/main.py", "score": 0.9},
        {"filename": "src/util.py", "score": 0.7},
    ]


def test_trace_search_map_json_out_includes_meta_only_case(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir()

    (traces_dir / "case_meta.meta.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "case_meta",
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 1,
                "semantic_hints": [{"filename": "/repo/src/only_hint.py", "score": 0.9}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        trace_main,
        [str(traces_dir), "--search-map", "--json-out", "-o", "search_map.json"],
    )

    assert result.exit_code == 0
    payload = json.loads((tmp_path / "reports" / "search_map.json").read_text(encoding="utf-8"))
    assert payload["summary"]["cases"] == 1
    assert payload["summary"]["cases_with_semantic_hints"] == 1
    assert payload["cases"][0]["case_id"] == "case_meta"
    assert payload["cases"][0]["turn_summaries"] == []
    assert payload["cases"][0]["semantic_hints"] == [{"filename": "src/only_hint.py", "score": 0.9}]


def test_trace_search_map_json_out_joins_dataset_and_results(tmp_path: Path) -> None:
    experiment_root = tmp_path
    traces_dir = experiment_root / "traces"
    results_dir = experiment_root / "results"
    reports_dir = experiment_root / "reports"
    traces_dir.mkdir()
    results_dir.mkdir()
    reports_dir.mkdir()

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "case_1",
                "query": "find handler",
                "repo": "example/repo",
                "base_commit": "deadbeef",
                "hard_gt": [
                    {
                        "path": "src/main.py",
                        "function": "handler",
                        "range": [10, 20],
                        "target_ranges": [[10, 12]],
                        "signature": "def handler()",
                    }
                ],
                "soft_context": [
                    {
                        "path": "src/util.py",
                        "function": "helper",
                        "range": [1, 5],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (results_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "case_id": "case_1",
                "repo": "example/repo",
                "completed": True,
                "partial": False,
                "turns_used": 2,
                "latency_s": 1.2,
                "file_recall": 1.0,
                "file_precision": 0.5,
                "line_coverage": 1.0,
                "line_precision_matched": 0.5,
                "context_line_coverage": 1.0,
                "context_line_precision_matched": 0.5,
                "function_hit_rate": 1.0,
                "functions_hit": 1,
                "functions_total": 1,
                "returned_files_count": 2,
                "search_mode": "agentic",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": "run",
                        "name": "run-a",
                        "root": str(experiment_root),
                    },
                    "run": {
                        "search_mode": "agentic",
                    },
                    "search": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "max_turns": 8,
                        "temperature": 0.2,
                        "prompt_file": "search_openai.yaml",
                    },
                    "retrieval": {
                        "backend": "auto",
                    },
                    "dataset": {
                        "dataset_path": str(dataset_path),
                    },
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    trace_path = traces_dir / "case_1.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "turn": 1,
                "llm_latency_ms": 10.0,
                "llm_response": {"usage": {"prompt_tokens": 11, "completion_tokens": 7}},
                "tool_calls_raw": [
                    {
                        "id": "t1",
                        "function": {
                            "name": "grep_search",
                            "arguments": json.dumps({"query": "handler"}),
                        },
                    }
                ],
                "tool_results": [
                    {
                        "id": "t1",
                        "name": "grep_search",
                        "result": "/repo/src/main.py:10:def handler():",
                        "success": True,
                        "latency_ms": 3.0,
                    }
                ],
                "report_back": None,
            }
        )
        + "\n"
        + json.dumps(
            {
                "turn": 2,
                "llm_latency_ms": 12.0,
                "llm_response": {"usage": {"prompt_tokens": 9, "completion_tokens": 4}},
                "tool_calls_raw": [
                    {
                        "id": "t2",
                        "function": {
                            "name": "report_back",
                            "arguments": json.dumps(
                                {
                                    "explanation": "found",
                                    "files": {"/repo/src/main.py": [[10, 12]]},
                                }
                            ),
                        },
                    }
                ],
                "tool_results": [
                    {
                        "id": "t2",
                        "name": "report_back",
                        "result": '{"ok": true}',
                        "success": True,
                        "latency_ms": 1.0,
                    }
                ],
                "report_back": {"explanation": "found", "files": {"/repo/src/main.py": [[10, 12]]}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trace_path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "case_1",
                "repo": "example/repo",
                "query": "find handler",
                "search_mode": "agentic",
                "semantic_hints_used": 0,
                "semantic_hints": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        trace_main,
        [str(experiment_root), "--search-map", "--json-out", "-o", "search_map.bundle.json"],
    )

    assert result.exit_code == 0
    payload = json.loads((reports_dir / "search_map.bundle.json").read_text(encoding="utf-8"))
    assert payload["kind"] == "search_map_bundle"
    assert payload["experiment"]["search"]["model"] == "gpt-5-mini"
    assert payload["cases"][0]["query"] == "find handler"
    assert payload["cases"][0]["ground_truth_files"] == {"src/main.py": [[10, 12]]}
    assert payload["cases"][0]["metrics_snapshot"]["file_recall"] == 1.0
    assert payload["cases"][0]["turn_summaries"][0]["tool_names"] == ["grep_search"]
    assert payload["cases"][0]["file_blocks"][0]["path"] == "src/main.py"
    assert payload["cases"][0]["events"][0]["tool_query"] == "handler"


def test_trace_validate_json_out_reports_metadata_only_case(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir()

    (traces_dir / "case_meta.meta.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "case_meta",
                "repo": "example/repo",
                "search_mode": "indexed",
                "semantic_hints_used": 0,
                "semantic_hints": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        trace_main,
        [str(traces_dir), "--validate", "--json-out", "-o", "validate.json"],
    )

    assert result.exit_code == 0
    payload = json.loads((tmp_path / "reports" / "validate.json").read_text(encoding="utf-8"))
    assert payload["total_cases"] == 1
    assert payload["valid_cases"] == 1
    assert payload["total_warnings"] >= 1
    assert "metadata-only case" in payload["results"][0]["warnings"][0]
