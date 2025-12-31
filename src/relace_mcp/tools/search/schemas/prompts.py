from relace_mcp.lsp.languages import LANGUAGE_CONFIGS


def build_find_symbol_section(languages: frozenset[str]) -> str:
    """Build the find_symbol tool description section for system prompt."""
    if not languages:
        return ""

    lang_names = sorted(languages)
    exts: list[str] = []
    for lang in lang_names:
        if lang in LANGUAGE_CONFIGS:
            exts.extend(LANGUAGE_CONFIGS[lang].file_extensions)

    return (
        f"- `find_symbol`: Trace {', '.join(lang_names)} symbol definitions/references\n"
        f"    - Supported: {', '.join(exts)}\n"
        "    - Requires file path, line, column (1-indexed)"
    )


def build_system_prompt(template: str, languages: frozenset[str]) -> str:
    """Build system prompt with dynamic find_symbol section."""
    section = build_find_symbol_section(languages)
    return template.replace("{find_symbol_section}", section)
