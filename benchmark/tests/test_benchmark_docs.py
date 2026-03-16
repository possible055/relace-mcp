from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "doc_path",
    [
        Path("docs/benchmark.md"),
        Path("docs/benchmark.zh-CN.md"),
    ],
)
def test_benchmark_docs_match_current_cli_contract(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "uv run --extra benchmark python -m benchmark.cli.build_locbench" in text
    assert "uv run --extra benchmark python -m benchmark.cli.curate --count 50" in text
    assert "--max-turns 4 --max-turns 6 --max-turns 8" in text
    assert "--prompt-file" in text
    assert "--search-prompt-file" not in text
    assert "uv run --extra dev --extra benchmark pytest benchmark/tests -v" in text
    assert "| Line Precision |" not in text
    assert "benchmark.cli.trace" in text
    assert "--latest --search-map --json-out -o search_map.json" in text
    assert "--latest --validate" in text
    assert "<case_id>.meta.json" in text
    assert "metadata.artifacts" in text
    assert "artifacts/experiments/<experiment_name>" in text
    assert "results/results.jsonl" in text
