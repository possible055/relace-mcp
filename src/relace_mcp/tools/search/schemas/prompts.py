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


def build_system_prompt(
    template: str, languages: frozenset[str], enabled_tools: set[str] | None = None
) -> str:
    """Build system prompt with dynamic tool sections (find_symbol, bash)."""
    # 1. find_symbol
    fs_section = build_find_symbol_section(languages)
    prompt = template.replace("{find_symbol_section}", fs_section)

    # 2. bash
    bash_section = ""
    if enabled_tools is not None and "bash" in enabled_tools:
        bash_section = "- `bash`: Shell commands (use sparingly, if available)"

    # Also handle cleaning up empty line if bash is disabled
    prompt = prompt.replace("{bash_section}", bash_section)

    # Cleanup any resulting triple-newlines
    return prompt.replace("\n\n\n", "\n\n").strip()
