from pathlib import Path

from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.languages.python import PYTHON_CONFIG

# Registry of supported language configurations
LANGUAGE_CONFIGS: dict[str, LanguageServerConfig] = {
    "python": PYTHON_CONFIG,
}

# Cache for detected LSP languages per base_dir
_lsp_cache: dict[Path, frozenset[str]] = {}


def get_config_for_file(path: str) -> LanguageServerConfig | None:
    """Get the language configuration for a file path."""
    for config in LANGUAGE_CONFIGS.values():
        if config.matches_file(path):
            return config
    return None


def _detect_lsp_languages(base_dir: Path) -> frozenset[str]:
    """Scan directory for supported language files."""
    available: set[str] = set()
    for lang_id, config in LANGUAGE_CONFIGS.items():
        for ext in config.file_extensions:
            try:
                next(base_dir.rglob(f"*{ext}"))
                available.add(lang_id)
                break
            except StopIteration:
                continue
    return frozenset(available)


def get_lsp_languages(base_dir: Path) -> frozenset[str]:
    """Get available LSP languages for base_dir (cached)."""
    resolved = base_dir.resolve()

    if resolved in _lsp_cache:
        return _lsp_cache[resolved]

    languages = _detect_lsp_languages(resolved)
    _lsp_cache[resolved] = languages
    return languages


def clear_lsp_cache(base_dir: Path | None = None) -> None:
    """Clear cache for specific dir or all."""
    if base_dir is None:
        _lsp_cache.clear()
    else:
        _lsp_cache.pop(base_dir.resolve(), None)


__all__ = [
    "LanguageServerConfig",
    "PYTHON_CONFIG",
    "LANGUAGE_CONFIGS",
    "get_config_for_file",
    "get_lsp_languages",
    "clear_lsp_cache",
]
