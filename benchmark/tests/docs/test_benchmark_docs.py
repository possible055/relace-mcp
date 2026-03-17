from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "doc_path",
    [
        Path("docs/benchmark.md"),
        Path("docs/benchmark.zh-CN.md"),
    ],
)
def test_benchmark_docs_publish_supported_test_contract(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "uv run --extra dev --extra benchmark pytest benchmark/tests -q" in text
    assert "├── tests/" in text
    assert "├── analysis/" in text
    assert "├── cli/" in text
    assert "├── runner/" in text
