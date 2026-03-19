import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from benchmark.web import create_app


def _write_bundle(
    experiment_root: Path,
    *,
    experiment_name: str,
    experiment_type: str = "run",
    provider: str = "openai",
    model: str = "gpt-5-mini",
    search_mode: str = "agentic",
    max_turns: int = 8,
    temperature: float = 0.2,
    cases: list[dict] | None = None,
) -> None:
    reports_dir = experiment_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "kind": "search_map_bundle",
        "experiment": {
            "name": experiment_name,
            "root": str(experiment_root),
            "type": experiment_type,
            "search": {
                "provider": provider,
                "model": model,
                "max_turns": max_turns,
                "temperature": temperature,
            },
            "run": {
                "search_mode": search_mode,
            },
        },
        "summary": {
            "cases": len(cases or []),
        },
        "cases": cases or [],
    }
    (reports_dir / "search_map.bundle.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_health_and_static_fallback(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert (
        "Relace Benchmark Web" in root_response.text
        or '<div id="root"></div>' in root_response.text
    )


def test_experiments_endpoint_lists_runs_and_grid(tmp_path: Path) -> None:
    run_root = tmp_path / "run-a"
    grid_root = tmp_path / "grid-a"
    _write_bundle(run_root, experiment_name="run-a")
    (run_root / "reports" / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": "run",
                        "name": "run-a",
                        "root": str(run_root),
                    },
                    "search": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "max_turns": 8,
                        "temperature": 0.2,
                    },
                    "run": {
                        "search_mode": "agentic",
                        "cases_loaded": 2,
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (grid_root / "reports").mkdir(parents=True, exist_ok=True)
    (grid_root / "reports" / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": "grid",
                        "name": "grid-a",
                        "root": str(grid_root),
                    },
                    "search": {
                        "provider": "openai",
                        "model": "gpt-5.4",
                        "max_turns": 12,
                        "temperature": 0.0,
                    },
                    "run": {
                        "search_mode": "agentic",
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/api/experiments")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    names = {item["name"] for item in payload}
    assert names == {"run-a", "grid-a"}
    run_item = next(item for item in payload if item["name"] == "run-a")
    assert run_item["has_bundle"] is True
    assert run_item["case_count"] == 0


def test_search_map_bundle_endpoint_lazy_builds_from_experiment(tmp_path: Path) -> None:
    experiment_root = tmp_path / "run-lazy"
    traces_dir = experiment_root / "traces"
    reports_dir = experiment_root / "reports"
    results_dir = experiment_root / "results"
    traces_dir.mkdir(parents=True)
    reports_dir.mkdir()
    results_dir.mkdir()

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
                    }
                ],
                "soft_context": [],
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
                        "name": "run-lazy",
                        "root": str(experiment_root),
                    },
                    "search": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "max_turns": 8,
                        "temperature": 0.2,
                    },
                    "run": {
                        "search_mode": "agentic",
                    },
                    "dataset": {
                        "dataset_path": str(dataset_path),
                    },
                }
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
                "latency_s": 1.1,
                "file_recall": 1.0,
                "file_precision": 0.5,
                "line_coverage": 1.0,
                "line_precision_matched": 0.5,
                "context_line_coverage": 1.0,
                "context_line_precision_matched": 0.5,
                "function_hit_rate": 1.0,
                "functions_hit": 1,
                "functions_total": 1,
                "returned_files_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (traces_dir / "case_1.jsonl").write_text(
        json.dumps(
            {
                "turn": 1,
                "llm_latency_ms": 10.0,
                "llm_response": {"usage": {"prompt_tokens": 4, "completion_tokens": 2}},
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
                        "latency_ms": 1.0,
                    }
                ],
                "report_back": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (traces_dir / "case_1.meta.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
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

    client = TestClient(create_app(tmp_path))
    response = client.post("/api/search-map/bundle", json={"experiment_root": str(experiment_root)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "search_map_bundle"
    assert payload["cases"][0]["case_id"] == "case_1"
    assert payload["cases"][0]["query"] == "find handler"


def test_case_compare_endpoint_returns_compare_payload(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    case_payload = {
        "case_id": "case_1",
        "query": "find handler",
        "repo": "example/repo",
        "ground_truth_files": {"src/main.py": [[10, 12]]},
        "ground_truth_functions": [],
        "ground_truth_context_files": {},
        "semantic_hints": [],
        "selected_files": ["src/main.py"],
        "unique_files": ["src/main.py"],
        "unique_functions": [],
        "file_blocks": [
            {
                "path": "src/main.py",
                "block_kind": "select",
                "ranges": [[10, 12]],
                "first_turn": 1,
                "last_turn": 1,
                "event_count": 1,
                "source_tools": ["report_back"],
                "symbols": [],
                "functions": [],
            }
        ],
        "function_blocks": [],
        "turn_summaries": [
            {
                "turn": 1,
                "new_files": ["src/main.py"],
                "new_functions": [],
                "tool_names": ["report_back"],
            }
        ],
        "metrics_snapshot": {"file_recall": 1.0},
        "result_status": "ok",
    }
    _write_bundle(run_a, experiment_name="run-a", cases=[case_payload])
    _write_bundle(run_b, experiment_name="run-b", cases=[case_payload])

    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/case-map/compare",
        json={"case_id": "case_1", "experiment_roots": [str(run_a), str(run_b)]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "case_map_compare"
    assert payload["case_id"] == "case_1"
    assert len(payload["runs"]) == 2
