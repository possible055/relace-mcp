from pathlib import Path

import pytest

README_DOCS = [
    Path("README.md"),
    Path("README.zh-CN.md"),
]

README_SUBTOOL_DOCS = [
    (
        Path("README.md"),
        "do not add new top-level entries to `list_tools()`",
    ),
    (
        Path("README.zh-CN.md"),
        "不会给 `list_tools()` 新增 top-level 条目",
    ),
]

DASHBOARD_DOCS = [
    Path("docs/dashboard.md"),
    Path("docs/dashboard.zh-CN.md"),
]

TOOLS_DOCS = [
    (
        Path("docs/tools.md"),
        "Available only when `RELACE_CLOUD_TOOLS=1`.",
        "Available only when `MCP_SEARCH_RETRIEVAL=1`.",
        "These do not appear as standalone top-level MCP tools in `list_tools()`.",
    ),
    (
        Path("docs/tools.zh-CN.md"),
        "仅在 `RELACE_CLOUD_TOOLS=1` 时可用。",
        "仅在 `MCP_SEARCH_RETRIEVAL=1` 时可用。",
        "它们不会作为独立的 top-level MCP tools 出现在 `list_tools()` 里。",
    ),
]

ADVANCED_DOCS = [
    (
        Path("docs/advanced.md"),
        "does not trigger Codanna reindexing after every `fast_apply` edit",
        "does not trigger ChunkHound scans after every `fast_apply` edit",
    ),
    (
        Path("docs/advanced.zh-CN.md"),
        "不会在每次 `fast_apply` 编辑后自动触发 Codanna reindex",
        "不会在每次 `fast_apply` 编辑后自动触发 ChunkHound scan",
    ),
]


@pytest.mark.parametrize("doc_path", README_DOCS)
def test_readmes_publish_repo_local_benchmark_contract(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "uv sync --extra benchmark" in text
    assert "pip install relace-mcp[benchmark]" not in text
    assert "CONNECTION_TIMEOUT" not in text
    assert "SYNTAX_ERROR" not in text
    assert "NO_MATCH_FOUND" not in text
    assert "CLOUD_NOT_SYNCED" not in text
    assert "CONFLICT_DETECTED" not in text


@pytest.mark.parametrize(("doc_path", "phrase"), README_SUBTOOL_DOCS)
def test_readmes_clarify_search_subtool_flags(doc_path: Path, phrase: str) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert phrase in text
    assert "SEARCH_BASH_TOOLS" in text
    assert "SEARCH_LSP_TOOLS" in text
    assert "`agentic_search` / `agentic_retrieval`" in text


@pytest.mark.parametrize("doc_path", DASHBOARD_DOCS)
def test_dashboard_docs_publish_only_relogs_entrypoint(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "relogs" in text
    assert "python -m relace_mcp.dashboard" not in text


@pytest.mark.parametrize(
    ("doc_path", "cloud_phrase", "retrieval_phrase", "internal_phrase"),
    TOOLS_DOCS,
)
def test_tools_docs_publish_gated_tools_and_return_contracts(
    doc_path: Path,
    cloud_phrase: str,
    retrieval_phrase: str,
    internal_phrase: str,
) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert cloud_phrase in text
    assert retrieval_phrase in text
    assert internal_phrase in text
    assert "`view_file`" in text
    assert "`view_directory`" in text
    assert "`grep_search`" in text
    assert "`report_back`" in text
    assert "`bash`" in text
    assert "`find_symbol`" in text
    assert "`search_symbol`" in text
    assert "`status`" in text
    assert "`message`" in text
    assert "`path`" in text
    assert "`trace_id`" in text
    assert "`timing_ms`" in text
    assert "`diff`" in text
    assert "`auto_index`" in text
    assert "`has_more`" in text
    assert "`created_at`" in text
    assert "`updated_at`" in text


@pytest.mark.parametrize(
    ("doc_path", "codanna_phrase", "chunkhound_phrase"),
    ADVANCED_DOCS,
)
def test_advanced_docs_publish_current_retrieval_and_lsp_contracts(
    doc_path: Path,
    codanna_phrase: str,
    chunkhound_phrase: str,
) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "APPLY_API_KEY" in text
    assert "SEARCH_API_KEY" in text
    assert codanna_phrase in text
    assert chunkhound_phrase in text
    assert "`find_symbol`" in text
    assert "`search_symbol`" in text
    assert "get_type" not in text
    assert "list_symbols" not in text
    assert "call_graph" not in text
