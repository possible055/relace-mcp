from dataclasses import dataclass

from relace_mcp.lsp.languages import detect_available_lsp_servers

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}

# LSP tool names for easy reference
_LSP_TOOL_NAMES = frozenset(
    {"find_symbol", "search_symbol", "get_type", "list_symbols", "call_graph"}
)

# Basic tools that are always available
_BASIC_TOOLS = frozenset({"view_file", "view_directory", "grep_search", "glob", "report_back"})


@dataclass(frozen=True)
class ToolConfig:
    """Tool configuration data class."""

    enabled_tools: frozenset[str]
    include_strict: bool


class ToolConfigResolver:
    """Resolves tool configuration with support for environment variable injection for testing."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        lsp_languages: frozenset[str] | None = None,
        bash_available: bool = True,
    ) -> None:
        self._env = env
        self._lsp_languages = lsp_languages
        self._bash_available = bash_available

    def resolve(self) -> ToolConfig:
        """Resolve and return tool configuration."""
        lsp_mode = self._resolve_lsp_mode()
        enabled = self._resolve_enabled_tools(lsp_mode)
        return ToolConfig(
            enabled_tools=enabled,
            include_strict=self._resolve_strict_mode(),
        )

    def _resolve_lsp_mode(self) -> str:
        """Resolve LSP tools mode from environment."""
        raw = self._env.get("SEARCH_LSP_TOOLS", "").strip().lower() if self._env else ""
        if raw in _TRUTHY:
            return "true"
        if raw == "auto":
            return "auto"
        return "false"

    def _detect_lsp_servers(self) -> frozenset[str] | None:
        """Auto-detect available LSP servers."""
        if self._env is not None and "SEARCH_LSP_TOOLS" in self._env:
            available = detect_available_lsp_servers()
            return available if available else None
        return None

    def _resolve_enabled_tools(self, lsp_mode: str) -> frozenset[str]:
        """Resolve the set of enabled tools based on configuration."""
        raw_allowlist = self._env.get("SEARCH_ENABLED_TOOLS", "").strip() if self._env else ""

        # Determine if LSP tools should be enabled
        lsp_enabled = False
        lsp_available_languages: frozenset[str] | None = None

        if lsp_mode == "true":
            lsp_enabled = True
        elif lsp_mode == "auto":
            available_servers = self._detect_lsp_servers()
            if available_servers:
                lsp_enabled = True
                lsp_available_languages = available_servers

        # Parse allowlist
        if raw_allowlist:
            enabled = {
                t.strip().lower()
                for t in raw_allowlist.replace(",", " ").replace(";", " ").split()
                if t.strip()
            }
        else:
            enabled = set(_BASIC_TOOLS)
            if lsp_enabled:
                enabled.update(_LSP_TOOL_NAMES)

        # Apply filtering rules
        if not lsp_enabled:
            enabled -= _LSP_TOOL_NAMES

        # Always ensure report_back is present
        enabled.add("report_back")

        # bash requires platform support
        if "bash" in enabled and not self._bash_available:
            enabled.discard("bash")

        # Hide LSP tools if no LSP languages available for this project
        if self._lsp_languages is not None and not self._lsp_languages:
            enabled -= _LSP_TOOL_NAMES

        # In auto mode, check for language overlap
        if lsp_available_languages is not None and self._lsp_languages is not None:
            if not (lsp_available_languages & self._lsp_languages):
                enabled -= _LSP_TOOL_NAMES

        return frozenset(enabled)

    def _resolve_strict_mode(self) -> bool:
        """Resolve whether to include strict field in schemas."""
        raw = self._env.get("SEARCH_TOOL_STRICT", "1").strip().lower() if self._env else "1"
        if raw in _TRUTHY:
            return True
        if raw in _FALSY:
            return False
        return True


def get_tool_config(
    env: dict[str, str] | None = None,
    lsp_languages: frozenset[str] | None = None,
    bash_available: bool = True,
) -> ToolConfig:
    """Get tool configuration.

    Args:
        env: Environment variables dictionary, None to use os.environ.
        lsp_languages: Set of available LSP languages.
        bash_available: Whether bash is available.

    Returns:
        ToolConfig instance.
    """
    import os

    effective_env = env if env is not None else dict(os.environ)
    resolver = ToolConfigResolver(
        env=effective_env,
        lsp_languages=lsp_languages,
        bash_available=bash_available,
    )
    return resolver.resolve()
