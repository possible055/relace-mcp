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

    initialization_options: dict[str, Any] = field(default_factory=dict)
    """Additional options to send during initialization."""

    workspace_config: dict[str, Any] = field(default_factory=dict)
    """Workspace configuration settings."""

    def matches_file(self, path: str) -> bool:
        """Check if this config handles the given file path."""
        return any(path.endswith(ext) for ext in self.file_extensions)
