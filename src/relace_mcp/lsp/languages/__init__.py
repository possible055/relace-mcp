import os
from pathlib import Path

from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.languages.go import GO_CONFIG
from relace_mcp.lsp.languages.python import PYTHON_CONFIG
from relace_mcp.lsp.languages.rust import RUST_CONFIG
from relace_mcp.lsp.languages.typescript import TYPESCRIPT_CONFIG

# Registry of supported language configurations
LANGUAGE_CONFIGS: dict[str, LanguageServerConfig] = {
    "python": PYTHON_CONFIG,
    "typescript": TYPESCRIPT_CONFIG,
    "go": GO_CONFIG,
    "rust": RUST_CONFIG,
}

# Cache for detected LSP languages per base_dir
_lsp_cache: dict[Path, frozenset[str]] = {}

# Directories ignored during language detection (performance + symlink safety).
_DETECTION_IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".direnv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "target",
        "venv",
    }
)


def get_config_for_file(path: str) -> LanguageServerConfig | None:
    """Get the language configuration for a file path."""
    for config in LANGUAGE_CONFIGS.values():
        if config.matches_file(path):
            return config
    return None


def get_lsp_languages(base_dir: Path) -> frozenset[str]:
    """Get available LSP languages for base_dir (cached)."""
    resolved = base_dir.resolve()
    if resolved in _lsp_cache:
        return _lsp_cache[resolved]

    if not resolved.is_dir():
        languages: frozenset[str] = frozenset()
        _lsp_cache[resolved] = languages
        return languages

    # Build a suffix -> language_id map for quick matching.
    ext_to_langs: dict[str, set[str]] = {}
    for lang_id, config in LANGUAGE_CONFIGS.items():
        for ext in config.file_extensions:
            ext_to_langs.setdefault(ext.lower(), set()).add(lang_id)

    available: set[str] = set()
    wanted = set(LANGUAGE_CONFIGS.keys())

    for _root, dirs, files in os.walk(resolved, followlinks=False):
        # Avoid huge dependency dirs and caches.
        dirs[:] = [d for d in dirs if d not in _DETECTION_IGNORED_DIR_NAMES]

        for name in files:
            lower = name.lower()
            for ext, langs in ext_to_langs.items():
                if lower.endswith(ext):
                    available.update(langs)
            if available >= wanted:
                break

        if available >= wanted:
            break

    languages = frozenset(available)
    _lsp_cache[resolved] = languages
    return languages


def detect_available_lsp_servers() -> frozenset[str]:
    """Detect which LSP servers are available in the current environment.

    Checks if the LSP server executable for each supported language
    is available in the system PATH.

    Returns:
        Set of language IDs (e.g., {"python", "go"}) for which
        the LSP server is installed.
    """
    import shutil

    available: set[str] = set()
    for lang_id, config in LANGUAGE_CONFIGS.items():
        if config.command and shutil.which(config.command[0]):
            available.add(lang_id)
    return frozenset(available)


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
    "detect_available_lsp_servers",
    "clear_lsp_cache",
]
