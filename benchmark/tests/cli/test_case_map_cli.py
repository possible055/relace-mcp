import json
from pathlib import Path

from click.testing import CliRunner

from benchmark.cli.case_map import main as case_map_main


def _write_bundle(
    experiment_root: Path,
    *,
    experiment_name: str,
    provider: str,
    model: str,
    search_mode: str,
    max_turns: int,
    temperature: float,
    cases: list[dict],
) -> None:
    reports_dir = experiment_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "kind": "search_map_bundle",
        "experiment": {
            "name": experiment_name,
            "root": str(experiment_root),
            "type": "run",
            "search": {
                "provider": provider,
                "model": model,
                "max_turns": max_turns,
                "temperature": temperature,
            },
            "run": {
                "search_mode": search_mode,
            },
            "retrieval": {
                "backend": "auto",
            },
        },
        "summary": {
            "cases": len(cases),
        },
        "cases": cases,
    }
    (reports_dir / "search_map.bundle.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_case_map_cli_compares_arbitrary_runs(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    base_case = {
        "case_id": "case_1",
        "query": "find handler",
        "repo": "example/repo",
        "ground_truth_files": {"src/main.py": [[10, 12]]},
        "ground_truth_functions": [],
        "ground_truth_context_files": {"src/main.py": [[10, 20]]},
        "semantic_hints": [{"filename": "src/main.py", "score": 0.9}],
        "selected_files": ["src/main.py"],
        "unique_files": ["src/main.py", "src/util.py"],
        "unique_functions": [],
        "file_blocks": [
            {
                "path": "src/main.py",
                "block_kind": "grep_hit",
                "ranges": [[10, 10]],
                "first_turn": 1,
                "last_turn": 1,
                "event_count": 1,
                "source_tools": ["grep_search"],
                "symbols": [],
                "functions": [],
            },
            {
                "path": "src/main.py",
                "block_kind": "select",
                "ranges": [[10, 12]],
                "first_turn": 2,
                "last_turn": 2,
                "event_count": 1,
                "source_tools": ["report_back"],
                "symbols": [],
                "functions": [],
            },
        ],
        "function_blocks": [],
        "turn_summaries": [
            {
                "turn": 1,
                "new_files": ["src/main.py"],
                "new_functions": [],
                "tool_names": ["grep_search"],
            },
            {
                "turn": 2,
                "new_files": ["src/util.py"],
                "new_functions": [],
                "tool_names": ["report_back"],
            },
        ],
        "metrics_snapshot": {
            "file_recall": 1.0,
            "file_precision": 0.5,
            "turns_used": 2,
            "latency_s": 1.2,
        },
        "result_status": "ok",
    }
    _write_bundle(
        run_a,
        experiment_name="run-a",
        provider="openai",
        model="gpt-5-mini",
        search_mode="agentic",
        max_turns=8,
        temperature=0.2,
        cases=[base_case],
    )
    run_b_case = dict(base_case)
    run_b_case["unique_files"] = ["src/main.py", "src/service.py"]
    run_b_case["file_blocks"] = [
        {
            "path": "src/main.py",
            "block_kind": "read",
            "ranges": [[10, 12]],
            "first_turn": 1,
            "last_turn": 1,
            "event_count": 1,
            "source_tools": ["view_file"],
            "symbols": [],
            "functions": [],
        }
    ]
    run_b_case["selected_files"] = ["src/main.py"]
    run_b_case["semantic_hints"] = [{"filename": "src/service.py", "score": 0.7}]
    run_b_case["turn_summaries"] = [
        {"turn": 1, "new_files": ["src/main.py"], "new_functions": [], "tool_names": ["view_file"]},
    ]
    run_b_case["metrics_snapshot"] = {
        "file_recall": 0.5,
        "file_precision": 0.5,
        "turns_used": 1,
        "latency_s": 0.8,
    }
    _write_bundle(
        run_b,
        experiment_name="run-b",
        provider="openai",
        model="gpt-5.4",
        search_mode="agentic",
        max_turns=12,
        temperature=0.0,
        cases=[run_b_case],
    )

    output_path = tmp_path / "case_map.json"
    runner = CliRunner()
    result = runner.invoke(
        case_map_main,
        [
            str(run_a),
            str(run_b),
            "--case-id",
            "case_1",
            "--json-out",
            "-o",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "case_map_compare"
    assert payload["case_id"] == "case_1"
    assert len(payload["runs"]) == 2
    assert payload["comparisons"]["shared_files"] == ["src/main.py"]
    assert payload["comparisons"]["unique_files_by_run"][payload["runs"][0]["run_label"]] == [
        "src/util.py"
    ]
    assert payload["comparisons"]["unique_files_by_run"][payload["runs"][1]["run_label"]] == [
        "src/service.py"
    ]
    assert payload["comparisons"]["selected_overlap"] == ["src/main.py"]
    assert "openai/gpt-5-mini" in payload["runs"][0]["run_label"]
    assert "turns=8" in payload["runs"][0]["run_label"]


def test_case_map_cli_expands_grid_report_and_marks_missing_case(tmp_path: Path) -> None:
    grid_root = tmp_path / "grid"
    run_a = grid_root / "runs" / "trial-a"
    run_b = grid_root / "runs" / "trial-b"
    _write_bundle(
        run_a,
        experiment_name="trial-a",
        provider="openai",
        model="gpt-5-mini",
        search_mode="agentic",
        max_turns=8,
        temperature=0.2,
        cases=[
            {
                "case_id": "case_1",
                "query": "find handler",
                "repo": "example/repo",
                "ground_truth_files": {},
                "ground_truth_functions": [],
                "ground_truth_context_files": {},
                "semantic_hints": [],
                "selected_files": [],
                "unique_files": ["src/main.py"],
                "unique_functions": [],
                "file_blocks": [],
                "function_blocks": [],
                "turn_summaries": [],
                "metrics_snapshot": {"file_recall": 1.0},
                "result_status": "ok",
            }
        ],
    )
    _write_bundle(
        run_b,
        experiment_name="trial-b",
        provider="openai",
        model="gpt-5.4",
        search_mode="agentic",
        max_turns=12,
        temperature=0.0,
        cases=[],
    )

    reports_dir = grid_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": "grid",
                        "name": "grid-a",
                        "root": str(grid_root),
                    }
                },
                "grid": {
                    "trials": [
                        {"paths": {"experiment_root": str(run_a)}},
                        {"paths": {"experiment_root": str(run_b)}},
                    ]
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        case_map_main,
        [
            str(reports_dir / "summary.report.json"),
            "--case-id",
            "case_1",
            "--json-out",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload["runs"]) == 2
    assert payload["runs"][1]["result_status"] == "missing_case"
    assert (
        payload["comparisons"]["path_matrix"][0]["runs"][payload["runs"][1]["run_label"]]["status"]
        == "missing_case"
    )
