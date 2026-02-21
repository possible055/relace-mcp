import os
from unittest import mock

import pytest

from relace_mcp.tools.search.schemas import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_OPENAI,
    USER_PROMPT_TEMPLATE,
    USER_PROMPT_TEMPLATE_OPENAI,
    build_system_prompt,
)


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_prompt_replaces_all_fragment_placeholders(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)

    for placeholder in (
        "{bash_tool}",
        "{lsp_tools}",
        "{lsp_strategy}",
        "{lsp_example}",
        "{bash_example}",
        "{example_calls_dynamic}",
        "{retrieval_workflow}",
    ):
        assert placeholder not in prompt


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_lsp_fragment_empty_when_no_languages(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)

    # The dynamic {lsp_tools} section should not inject any LSP tool lines
    for name in ("search_symbol", "get_type", "list_symbols", "call_graph"):
        assert f"`{name}`" not in prompt


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_bash_fragment_empty_when_not_enabled(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)

    assert "read-only operations" not in prompt


def test_prompt_includes_lsp_tools_when_enabled() -> None:
    enabled = {
        "view_file",
        "view_directory",
        "grep_search",
        "glob",
        "find_symbol",
        "search_symbol",
        "get_type",
        "list_symbols",
        "call_graph",
        "report_back",
    }
    prompt = build_system_prompt(SYSTEM_PROMPT, frozenset({"python"}), enabled)

    for name in ("find_symbol", "search_symbol", "get_type", "list_symbols", "call_graph"):
        assert f"`{name}`" in prompt


def test_bash_fragment_present_when_enabled() -> None:
    enabled = {"view_file", "grep_search", "glob", "bash", "report_back"}
    prompt = build_system_prompt(SYSTEM_PROMPT, frozenset(), enabled)

    assert "read-only operations" in prompt


# --- Retrieval context tests ---


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_retrieval_fragments_absent_without_context(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)

    assert "semantic hints" not in prompt.lower()


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_retrieval_fragments_present_with_context(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled, context={"retrieval": True})

    # retrieval_workflow is in both templates
    assert "hinted files" in prompt.lower()

    # retrieval_execution is only in relace template
    if "{retrieval_execution}" in template:
        assert "semantic hints" in prompt.lower()


# --- Unified user_prompt_template tests ---


@pytest.mark.parametrize("template", [USER_PROMPT_TEMPLATE, USER_PROMPT_TEMPLATE_OPENAI])
def test_user_prompt_template_has_semantic_hints_placeholder(template: str) -> None:
    assert "{semantic_hints_section}" in template


@pytest.mark.parametrize("template", [USER_PROMPT_TEMPLATE, USER_PROMPT_TEMPLATE_OPENAI])
def test_user_prompt_formats_without_hints(template: str) -> None:
    result = template.format(query="test query", semantic_hints_section="")
    assert "test query" in result
    assert "{semantic_hints_section}" not in result


@pytest.mark.parametrize("template", [USER_PROMPT_TEMPLATE, USER_PROMPT_TEMPLATE_OPENAI])
def test_user_prompt_formats_with_hints(template: str) -> None:
    hints = "<semantic_hints>\n- foo.py (score: 0.95)\n</semantic_hints>"
    result = template.format(query="test query", semantic_hints_section=hints)
    assert "test query" in result
    assert "foo.py" in result
    assert "semantic_hints" in result


# --- Environment variable override tests ---


def test_env_var_system_prompt_relace_override() -> None:
    custom_prompt = "Custom relace system prompt with {lsp_tools} and {bash_tool}"
    with mock.patch.dict(os.environ, {"SEARCH_SYSTEM_PROMPT_RELACE": custom_prompt}):
        # Re-import to pick up env var (test the resolution logic directly)
        from relace_mcp.config import _resolve_system_prompt

        result = _resolve_system_prompt("original yaml value", "SEARCH_SYSTEM_PROMPT_RELACE")
        assert result == custom_prompt


def test_env_var_system_prompt_falls_back_to_yaml() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        # Ensure the env var is not set
        os.environ.pop("SEARCH_SYSTEM_PROMPT_RELACE", None)
        from relace_mcp.config import _resolve_system_prompt

        result = _resolve_system_prompt("  original yaml value  ", "SEARCH_SYSTEM_PROMPT_RELACE")
        assert result == "original yaml value"
