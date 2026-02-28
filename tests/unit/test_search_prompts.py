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
def test_build_system_prompt_strips_triple_newlines(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)
    assert "\n\n\n" not in prompt


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_build_system_prompt_renders_max_turns(
    template: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_MAX_TURNS", "7")
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)
    assert "{max_turns}" not in prompt
    assert "You have 7 exploration turns maximum." in prompt


@pytest.mark.parametrize("template", [SYSTEM_PROMPT, SYSTEM_PROMPT_OPENAI])
def test_build_system_prompt_hides_bash_when_disabled(template: str) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(template, frozenset(), enabled)
    assert "`bash`" not in prompt


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
    custom_prompt = "Custom relace system prompt"
    with mock.patch.dict(os.environ, {"SEARCH_SYSTEM_PROMPT_RELACE": custom_prompt}):
        from relace_mcp.config import _resolve_system_prompt

        result = _resolve_system_prompt("original yaml value", "SEARCH_SYSTEM_PROMPT_RELACE")
        assert result == custom_prompt


def test_env_var_system_prompt_falls_back_to_yaml() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SEARCH_SYSTEM_PROMPT_RELACE", None)
        from relace_mcp.config import _resolve_system_prompt

        result = _resolve_system_prompt("  original yaml value  ", "SEARCH_SYSTEM_PROMPT_RELACE")
        assert result == "original yaml value"
