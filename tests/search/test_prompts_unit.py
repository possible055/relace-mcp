import pytest

import relace_mcp.config.settings as settings_mod
from relace_mcp.config import load_prompt_file
from relace_mcp.search.schemas import build_system_prompt

# --- Helper: load all 4 prompt variants ---

_PROMPT_NAMES = ["search_relace", "search_openai", "retrieval_relace", "retrieval_openai"]


@pytest.fixture(params=_PROMPT_NAMES)
def prompt_data(request: pytest.FixtureRequest) -> dict:
    data = load_prompt_file(request.param)
    data["_name"] = request.param
    return data


# --- build_system_prompt tests ---


def test_build_system_prompt_strips_triple_newlines(prompt_data: dict) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "report_back"}
    prompt = build_system_prompt(prompt_data["system_message_template"], enabled_tools=enabled)
    assert "\n\n\n" not in prompt


def test_build_system_prompt_renders_max_turns(
    prompt_data: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_mod, "SEARCH_MAX_TURNS", 7)
    enabled = {"view_file", "view_directory", "grep_search", "report_back"}
    prompt = build_system_prompt(prompt_data["system_message_template"], enabled_tools=enabled)
    assert "{max_turns}" not in prompt
    # Only retrieval prompts embed max_turns in the system message
    if "retrieval" in prompt_data["_name"]:
        assert "7" in prompt


def test_build_system_prompt_hides_bash_when_disabled(prompt_data: dict) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "report_back"}
    prompt = build_system_prompt(prompt_data["system_message_template"], enabled_tools=enabled)
    assert "`bash`" not in prompt


def test_build_system_prompt_keeps_bash_when_enabled(prompt_data: dict) -> None:
    enabled = {"view_file", "view_directory", "grep_search", "bash", "report_back"}
    prompt = build_system_prompt(prompt_data["system_message_template"], enabled_tools=enabled)
    assert "`bash`" in prompt
    assert "Pipes allowed" in prompt
    assert "outside `/repo` are blocked" in prompt


# --- LSP injection tests ---


def test_lsp_section_injected_when_has_lsp(prompt_data: dict) -> None:
    lsp_section = prompt_data.get("lsp_section", "")
    prompt = build_system_prompt(
        prompt_data["system_message_template"],
        has_lsp=True,
        lsp_section=lsp_section,
    )
    assert "{lsp_section}" not in prompt
    assert "search_symbol" in prompt


def test_lsp_section_removed_when_no_lsp(prompt_data: dict) -> None:
    prompt = build_system_prompt(
        prompt_data["system_message_template"],
        has_lsp=False,
        lsp_section=prompt_data.get("lsp_section", ""),
    )
    assert "{lsp_section}" not in prompt
    assert "search_symbol" not in prompt


def test_strategy_placeholders_resolved(prompt_data: dict) -> None:
    prompt = build_system_prompt(
        prompt_data["system_message_template"],
        has_lsp=False,
        lsp_section=prompt_data.get("lsp_section", ""),
        step2_discovery=prompt_data.get("step2_discovery"),
        step3_verification=prompt_data.get("step3_verification"),
    )
    assert "{step2_discovery}" not in prompt
    assert "{step3_verification}" not in prompt


def test_search_openai_strategy_switches_with_lsp() -> None:
    prompt_data = load_prompt_file("search_openai")

    prompt_no_lsp = build_system_prompt(
        prompt_data["system_message_template"],
        has_lsp=False,
        lsp_section=prompt_data.get("lsp_section", ""),
        step2_discovery=prompt_data.get("step2_discovery"),
        step3_verification=prompt_data.get("step3_verification"),
    )
    assert "Start with `grep_search` whenever the query includes textual anchors" in prompt_no_lsp
    assert "use `search_symbol` as the first call" not in prompt_no_lsp

    prompt_with_lsp = build_system_prompt(
        prompt_data["system_message_template"],
        has_lsp=True,
        lsp_section=prompt_data.get("lsp_section", ""),
        step2_discovery=prompt_data.get("step2_discovery"),
        step3_verification=prompt_data.get("step3_verification"),
    )
    assert "use `search_symbol` as the first call" in prompt_with_lsp


# --- user_message_template tests ---


def test_user_prompt_formats_query(prompt_data: dict) -> None:
    template = prompt_data["user_message_template"]
    format_kwargs: dict[str, str] = {"query": "test query", "max_turns": "5"}
    if "{freshness_message}" in template:
        format_kwargs["freshness_message"] = ""
        format_kwargs["hints_list"] = ""
    result = template.format(**format_kwargs)
    assert "test query" in result
    assert "{query}" not in result


# --- load_prompt_file tests ---


_RETRIEVAL_NAMES = ["retrieval_relace", "retrieval_openai"]
_ALL_NAMES = _PROMPT_NAMES


def test_load_prompt_file_returns_all_keys() -> None:
    for name in _ALL_NAMES:
        data = load_prompt_file(name)
        assert "system_message_template" in data
        assert "user_message_template" in data
        assert "turn_status_messages" in data
        assert "report_back_retry_message" in data


def test_retrieval_prompt_has_guidance_keys() -> None:
    for name in _RETRIEVAL_NAMES:
        data = load_prompt_file(name)
        assert "freshness_messages" in data
        assert "{freshness_message}" in data["user_message_template"]
        assert "{hints_list}" in data["user_message_template"]


def test_load_prompt_file_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown prompt name"):
        load_prompt_file("nonexistent_prompt")


def test_load_prompt_file_requires_prompt_setting_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(settings_mod, "SEARCH_PROMPT_FILE")

    with pytest.raises(RuntimeError, match="Prompt override setting 'SEARCH_PROMPT_FILE'"):
        load_prompt_file("search_relace")
