from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.languages.python import PYTHON_CONFIG

# Registry of supported language configurations
LANGUAGE_CONFIGS: dict[str, LanguageServerConfig] = {
    "python": PYTHON_CONFIG,
}


def get_config_for_file(path: str) -> LanguageServerConfig | None:
    """Get the language configuration for a file path."""
    for config in LANGUAGE_CONFIGS.values():
        if config.matches_file(path):
            return config
    return None


__all__ = [
    "LanguageServerConfig",
    "PYTHON_CONFIG",
    "LANGUAGE_CONFIGS",
    "get_config_for_file",
]
