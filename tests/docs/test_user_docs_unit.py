from pathlib import Path

import pytest

README_DOCS = [
    Path("README.md"),
    Path("README.zh-CN.md"),
]

TOOLS_DOCS = [
    (
        Path("docs/tools.md"),
        "Available only when `MCP_RETRIEVAL_BACKEND=relace`.",
        "Available only when `MCP_SEARCH_RETRIEVAL=1`.",
        "Search-Only Subtools",
    ),
    (
        Path("docs/tools.zh-CN.md"),
        "仅在 `MCP_RETRIEVAL_BACKEND=relace` 时可用。",
        "仅在 `MCP_SEARCH_RETRIEVAL=1` 时可用。",
        "Search-Only Subtools",
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

DASHBOARD_DOCS = [
    Path("docs/dashboard.md"),
    Path("docs/dashboard.zh-CN.md"),
]


@pytest.mark.parametrize("doc_path", README_DOCS)
def test_readmes_publish_repo_local_benchmark_contract(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "uv sync --extra benchmark" in text
    assert "SEARCH_BASH_TOOLS" in text
    assert "SEARCH_LSP_TOOLS" in text
    assert "pip install relace-mcp[benchmark]" not in text
    assert "CONNECTION_TIMEOUT" not in text
    assert "SYNTAX_ERROR" not in text
    assert "NO_MATCH_FOUND" not in text
    assert "CLOUD_NOT_SYNCED" not in text
    assert "CONFLICT_DETECTED" not in text
    assert "top-level entries to `list_tools()`" not in text
    assert "内部使用的 `bash` subtool" not in text
    assert "internal `bash` subtool" not in text
    assert "literal search path" not in text


@pytest.mark.parametrize("doc_path", DASHBOARD_DOCS)
def test_dashboard_docs_publish_only_relogs_entrypoint(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "relogs" in text
    assert "python -m relace_mcp.dashboard" not in text


@pytest.mark.parametrize(
    ("doc_path", "cloud_phrase", "retrieval_phrase", "internal_heading"),
    TOOLS_DOCS,
)
def test_tools_docs_stay_user_facing(
    doc_path: Path,
    cloud_phrase: str,
    retrieval_phrase: str,
    internal_heading: str,
) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert cloud_phrase in text
    assert retrieval_phrase in text
    assert "`fast_apply`" in text
    assert "`agentic_search`" in text
    assert "`index_status`" in text
    assert "`cloud_sync`" in text
    assert "`cloud_search`" in text
    assert "`cloud_list`" in text
    assert "`cloud_clear`" in text
    assert "`agentic_retrieval`" in text
    assert "`diff`" in text
    assert internal_heading not in text
    assert "`view_file`" not in text
    assert "`view_directory`" not in text
    assert "`grep_search`" not in text
    assert "`report_back`" not in text
    assert "`find_symbol`" not in text
    assert "`search_symbol`" not in text
    assert "`trace_id`" not in text
    assert "`status_code`" not in text
    assert "`error_code`" not in text
    assert "`retryable`" not in text
    assert "`auto_index`" not in text
    assert "`has_more`" not in text
    assert "`created_at`" not in text
    assert "`updated_at`" not in text


@pytest.mark.parametrize(
    ("doc_path", "codanna_phrase", "chunkhound_phrase"),
    ADVANCED_DOCS,
)
def test_advanced_docs_keep_user_facing_retrieval_guidance(
    doc_path: Path,
    codanna_phrase: str,
    chunkhound_phrase: str,
) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "APPLY_API_KEY" in text
    assert "SEARCH_API_KEY" in text
    assert "SEARCH_BASH_TOOLS" in text
    assert "SEARCH_LSP_TOOLS" in text
    assert "SEARCH_TOOL_STRICT" in text
    assert codanna_phrase not in text
    assert chunkhound_phrase not in text
    assert "`find_symbol`" not in text
    assert "`search_symbol`" not in text
    assert "get_type" not in text
    assert "list_symbols" not in text
    assert "call_graph" not in text
