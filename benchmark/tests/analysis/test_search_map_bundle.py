import json
from pathlib import Path

from benchmark.analysis.bundle import (
    _build_exploration_tree,
    _build_exploration_tree_from_case_payload,
    _load_results_by_case,
    load_search_map_bundle,
)


def _write_trace_case(experiment_root: Path, *, case_id: str = "case_1") -> None:
    traces_dir = experiment_root / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace_path = traces_dir / f"{case_id}.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "turn": 1,
                "llm_latency_ms": 5.0,
                "llm_response": {},
                "tool_calls_raw": [],
                "tool_results": [],
                "report_back": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trace_path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "case_id": case_id,
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


def test_load_search_map_bundle_rebuilds_when_bundle_json_is_corrupt(tmp_path: Path) -> None:
    experiment_root = tmp_path / "experiment"
    _write_trace_case(experiment_root)
    reports_dir = experiment_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "search-map.bundle.json").write_text("{\n", encoding="utf-8")

    payload = load_search_map_bundle(experiment_root)

    assert payload["kind"] == "search_map_bundle"
    assert payload["cases"][0]["case_id"] == "case_1"
    assert payload["cases"][0]["exploration_tree"]["kind"] == "case"


def test_load_results_by_case_skips_invalid_json_lines(tmp_path: Path) -> None:
    results_path = tmp_path / "results.jsonl"
    results_path.write_text(
        json.dumps({"case_id": "case_1", "status": "ok"})
        + "\n"
        + "{\n"
        + json.dumps({"case_id": "case_2", "status": "error"})
        + "\n",
        encoding="utf-8",
    )

    results = _load_results_by_case(results_path)

    assert set(results) == {"case_1", "case_2"}
    assert results["case_2"]["status"] == "error"


def test_build_exploration_tree_from_case_payload_consumes_no_id_events_once() -> None:
    tree = _build_exploration_tree_from_case_payload(
        {
            "case_id": "case_1",
            "query": "find handler",
            "repo": "example/repo",
            "result_status": "ok",
            "metrics_snapshot": {},
            "turn_summaries": [
                {
                    "turn": 1,
                    "tool_names": ["view_file", "view_file"],
                }
            ],
            "events": [
                {
                    "turn": 1,
                    "tool_name": "view_file",
                    "access_type": "read",
                    "path": "src/main.py",
                }
            ],
        }
    )

    tool_nodes = tree["children"][0]["children"]
    assert [child["label"] for child in tool_nodes[0]["children"]] == ["src/main.py"]
    assert tool_nodes[1]["children"] == []


def test_build_exploration_tree_consumes_orphan_no_id_events_once() -> None:
    tree = _build_exploration_tree(
        case_id="case_1",
        query="find handler",
        repo="example/repo",
        turns=[
            {
                "turn": 1,
                "llm_latency_ms": 5.0,
                "llm_response": {},
                "tool_calls_raw": [],
                "tool_results": [
                    {"name": "view_file", "success": True},
                    {"name": "view_file", "success": True},
                ],
            }
        ],
        events=[
            {
                "turn": 1,
                "tool_name": "view_file",
                "access_type": "read",
                "path": "src/main.py",
            }
        ],
        metrics_snapshot={},
        result_status="ok",
    )

    tool_nodes = tree["children"][0]["children"]
    assert [child["label"] for child in tool_nodes[0]["children"]] == ["src/main.py"]
    assert tool_nodes[1]["children"] == []
