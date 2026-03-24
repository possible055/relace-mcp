"""Tool registry for configuration-driven tool management.

Enables pluggable tool definitions without code changes.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self


class ToolCategory(StrEnum):
    """Tool categorization for analysis grouping."""

    SEARCH = "search"
    READ = "read"
    EDIT = "edit"
    EXECUTE = "execute"
    NAVIGATE = "navigate"
    OTHER = "other"


@dataclass
class ToolDefinition:
    """Definition of a tool for the benchmark system."""

    name: str
    display_name: str
    abbreviation: str
    category: ToolCategory
    description: str = ""
    produces_files: bool = True
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "abbreviation": self.abbreviation,
            "category": self.category.value,
            "description": self.description,
            "produces_files": self.produces_files,
            "aliases": self.aliases,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            abbreviation=data.get("abbreviation", data["name"][:2].upper()),
            category=ToolCategory(data.get("category", "other")),
            description=data.get("description", ""),
            produces_files=data.get("produces_files", True),
            aliases=data.get("aliases", []),
        )


# Default tool definitions
DEFAULT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="agentic_search",
        display_name="Agentic Search",
        abbreviation="AS",
        category=ToolCategory.SEARCH,
        description="AI-powered semantic code search",
        aliases=["fast_search", "search"],
    ),
    ToolDefinition(
        name="grep",
        display_name="Grep",
        abbreviation="GR",
        category=ToolCategory.SEARCH,
        description="Pattern-based text search",
        aliases=["rg", "ripgrep"],
    ),
    ToolDefinition(
        name="glob",
        display_name="Glob",
        abbreviation="GL",
        category=ToolCategory.SEARCH,
        description="File pattern matching",
        aliases=["find"],
    ),
    ToolDefinition(
        name="read_file",
        display_name="Read File",
        abbreviation="RD",
        category=ToolCategory.READ,
        description="Read file contents",
        aliases=["read", "cat"],
    ),
    ToolDefinition(
        name="list_directory",
        display_name="List Directory",
        abbreviation="LS",
        category=ToolCategory.NAVIGATE,
        description="List directory contents",
        aliases=["ls", "dir"],
    ),
    ToolDefinition(
        name="edit_file",
        display_name="Edit File",
        abbreviation="ED",
        category=ToolCategory.EDIT,
        description="Modify file contents",
        aliases=["edit", "write"],
    ),
    ToolDefinition(
        name="bash",
        display_name="Bash",
        abbreviation="SH",
        category=ToolCategory.EXECUTE,
        description="Execute shell commands",
        aliases=["shell", "exec"],
    ),
]


class ToolRegistry:
    """Registry for tool definitions with lookup support."""

    def __init__(self, tools: list[ToolDefinition] | None = None):
        self._tools: dict[str, ToolDefinition] = {}
        self._aliases: dict[str, str] = {}

        for tool in tools or DEFAULT_TOOLS:
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            self._aliases[alias] = tool.name

    def get(self, name: str) -> ToolDefinition | None:
        """Get tool by name or alias."""
        if name in self._tools:
            return self._tools[name]
        canonical = self._aliases.get(name)
        if canonical:
            return self._tools.get(canonical)
        return None

    def get_abbreviation(self, name: str) -> str:
        """Get tool abbreviation for display."""
        tool = self.get(name)
        if tool:
            return tool.abbreviation
        return name[:2].upper()

    def get_category(self, name: str) -> ToolCategory:
        """Get tool category."""
        tool = self.get(name)
        if tool:
            return tool.category
        return ToolCategory.OTHER

    def list_tools(self) -> list[ToolDefinition]:
        """Get all registered tools."""
        return list(self._tools.values())

    def list_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        """Get tools in a specific category."""
        return [t for t in self._tools.values() if t.category == category]

    def to_dict(self) -> dict[str, Any]:
        """Export registry as dictionary."""
        return {
            "tools": [t.to_dict() for t in self._tools.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create registry from dictionary."""
        tools = [ToolDefinition.from_dict(t) for t in data.get("tools", [])]
        return cls(tools=tools)

    @classmethod
    def default(cls) -> Self:
        """Create registry with default tools."""
        return cls(tools=DEFAULT_TOOLS)
