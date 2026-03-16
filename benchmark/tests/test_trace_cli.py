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
    output_path = traces_dir / "search_map.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["cases_with_semantic_hints"] == 1
    assert payload["avg_semantic_hints_per_case"] == 2.0
    assert payload["per_case"][0]["semantic_hints_files"] == ["src/main.py", "src/util.py"]
