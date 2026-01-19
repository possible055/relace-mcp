from dataclasses import dataclass, field
from typing import Any


@dataclass
class LanguageServerConfig:
    """Configuration for a language server.

    Defines how to start and communicate with a specific language server.
    """

    language_id: str
    """LSP language identifier (e.g., "python", "typescript")."""

    file_extensions: tuple[str, ...]
    """File extensions this server handles (e.g., (".py",))."""

    command: list[str]
    """Command to start the language server (e.g., ["basedpyright-langserver", "--stdio"])."""

    config_files: tuple[str, ...] = ()
    """Config files that should trigger a server restart when changed."""

    install_hint: str = ""
    """Install instructions for the language server executable."""

    initialization_options: dict[str, Any] = field(default_factory=dict)
    """Additional options to send during initialization."""

    workspace_config: dict[str, Any] = field(default_factory=dict)
    """Workspace configuration settings."""

    extension_language_map: dict[str, str] = field(default_factory=dict)
    """Optional mapping from file extension to languageId for multi-extension servers."""

    def matches_file(self, path: str) -> bool:
        """Check if this config handles the given file path."""
        return any(path.endswith(ext) for ext in self.file_extensions)

    def get_language_id(self, path: str) -> str:
        """Get the languageId for a file based on its extension."""
        if self.extension_language_map:
            for ext, lang_id in self.extension_language_map.items():
                if path.endswith(ext):
                    return lang_id
        return self.language_id
