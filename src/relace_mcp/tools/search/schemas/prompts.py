import logging
from pathlib import Path
from typing import Any

import yaml

from relace_mcp.lsp.languages import LANGUAGE_CONFIGS

logger = logging.getLogger(__name__)

_FRAGMENTS_PATH = Path(__file__).parent.parent.parent.parent / "prompts" / "system_fragments.yaml"
_fragments_cache: dict[str, list[dict[str, Any]]] | None = None


def _load_fragments() -> dict[str, list[dict[str, Any]]]:
    global _fragments_cache
    if _fragments_cache is not None:
        return _fragments_cache
    with _FRAGMENTS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _fragments_cache = data.get("sections", {})
    return _fragments_cache


def _evaluate_when(
    when: dict[str, Any],
    enabled_tools: set[str],
    lsp_languages: frozenset[str],
    context: dict[str, Any] | None = None,
) -> bool:
    if "lsp" in when and when["lsp"] and not lsp_languages:
        return False
    if "tools_all" in when:
        required = set(when["tools_all"])
        if not required.issubset(enabled_tools):
            return False
    if "tools_none" in when:
        excluded = set(when["tools_none"])
        if excluded & enabled_tools:
            return False
    if "retrieval" in when:
        ctx = context or {}
        if when["retrieval"] and not ctx.get("retrieval"):
            return False
    return True


def _resolve_text(text: str, lsp_languages: frozenset[str]) -> str:
    lang_names = sorted(lsp_languages)
    exts: list[str] = []
    for lang in lang_names:
        if lang in LANGUAGE_CONFIGS:
            exts.extend(LANGUAGE_CONFIGS[lang].file_extensions)
    text = text.replace("{lsp_language_names}", ", ".join(lang_names))
    text = text.replace("{lsp_exts}", ", ".join(exts))
    return text


def _render_section(
    section_name: str,
    enabled_tools: set[str],
    lsp_languages: frozenset[str],
    context: dict[str, Any] | None = None,
) -> str:
    fragments = _load_fragments()
    rules = fragments.get(section_name, [])
    parts: list[str] = []
    for rule in rules:
        when = rule.get("when", {})
        if _evaluate_when(when, enabled_tools, lsp_languages, context):
            parts.append(_resolve_text(rule["text"], lsp_languages))
    return "\n".join(parts).rstrip()


def build_system_prompt(
    template: str,
    languages: frozenset[str],
    enabled_tools: set[str] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    tools = enabled_tools or set()
    fragments = _load_fragments()
    prompt = template
    for section_name in fragments:
        placeholder = "{" + section_name + "}"
        if placeholder in prompt:
            rendered = _render_section(section_name, tools, languages, context)
            prompt = prompt.replace(placeholder, rendered)
    return prompt.replace("\n\n\n", "\n\n").strip()
