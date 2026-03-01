import pytest

from relace_mcp.config import load_prompt_file
from relace_mcp.tools.search.schemas import build_system_prompt

# --- Helper: load all 4 prompt variants ---

_PROMPT_NAMES = ["search_relace", "search_openai", "retrieval_relace", "retrieval_openai"]


@pytest.fixture(params=_PROMPT_NAMES)
def prompt_data(request: pytest.FixtureRequest) -> dict:
    data = load_prompt_file(request.param)
    data["_name"] = request.param
    return data


# --- build_system_prompt tests ---


def test_build_system_prompt_strips_triple_newlines(prompt_data: dict) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(prompt_data["system_prompt"], enabled_tools=enabled)
    assert "\n\n\n" not in prompt


def test_build_system_prompt_renders_max_turns(
    prompt_data: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_MAX_TURNS", "7")
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(prompt_data["system_prompt"], enabled_tools=enabled)
    assert "{max_turns}" not in prompt
    assert "You have 7 exploration turns maximum." in prompt


def test_build_system_prompt_hides_bash_when_disabled(prompt_data: dict) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back"}
    prompt = build_system_prompt(prompt_data["system_prompt"], enabled_tools=enabled)
    assert "`bash`" not in prompt


def test_build_system_prompt_keeps_bash_when_enabled(prompt_data: dict) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "glob", "bash", "report_back"}
    prompt = build_system_prompt(prompt_data["system_prompt"], enabled_tools=enabled)
    assert "`bash`" in prompt


# --- LSP injection tests ---


def test_lsp_section_injected_when_has_lsp(prompt_data: dict) -> None:
    lsp_section = prompt_data.get("lsp_section", "")
    prompt = build_system_prompt(
        prompt_data["system_prompt"],
        has_lsp=True,
        lsp_section=lsp_section,
    )
    assert "{lsp_section}" not in prompt
    assert "search_symbol" in prompt


def test_lsp_section_removed_when_no_lsp(prompt_data: dict) -> None:
    prompt = build_system_prompt(
        prompt_data["system_prompt"],
        has_lsp=False,
        lsp_section=prompt_data.get("lsp_section", ""),
    )
    assert "{lsp_section}" not in prompt
    assert "search_symbol" not in prompt


# --- user_prompt_template tests ---


def test_user_prompt_template_has_semantic_hints_placeholder(prompt_data: dict) -> None:
    template = prompt_data["user_prompt_template"]
    assert "{semantic_hints_section}" in template


def test_user_prompt_formats_without_hints(prompt_data: dict) -> None:
    template = prompt_data["user_prompt_template"]
    result = template.format(query="test query", semantic_hints_section="")
    assert "test query" in result
    assert "{semantic_hints_section}" not in result


def test_user_prompt_formats_with_hints(prompt_data: dict) -> None:
    template = prompt_data["user_prompt_template"]
    hints = "<semantic_hints>\n- foo.py (score: 0.95)\n</semantic_hints>"
    result = template.format(query="test query", semantic_hints_section=hints)
    assert "test query" in result
    assert "foo.py" in result
    assert "semantic_hints" in result


# --- load_prompt_file tests ---


def test_load_prompt_file_returns_all_keys() -> None:
    for name in _PROMPT_NAMES:
        data = load_prompt_file(name)
        assert "system_prompt" in data
        assert "user_prompt_template" in data
        assert "turn_hint_template" in data
        assert "turn_instructions" in data
        assert "lsp_section" in data


def test_load_prompt_file_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown prompt name"):
        load_prompt_file("nonexistent_prompt")
