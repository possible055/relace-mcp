"""Tests for ToolRegistry."""

import pytest

from benchmark.domain.tools.registry import (
    DEFAULT_TOOLS,
    ToolCategory,
    ToolDefinition,
    ToolRegistry,
)


class TestToolCategory:
    def test_values(self):
        assert ToolCategory.SEARCH.value == "search"
        assert ToolCategory.READ.value == "read"
        assert ToolCategory.EDIT.value == "edit"


class TestToolDefinition:
    def test_to_dict(self):
        tool = ToolDefinition(
            name="grep",
            display_name="Grep",
            abbreviation="GR",
            category=ToolCategory.SEARCH,
            aliases=["rg"],
        )
        d = tool.to_dict()
        assert d["name"] == "grep"
        assert d["abbreviation"] == "GR"
        assert d["category"] == "search"
        assert d["aliases"] == ["rg"]

    def test_from_dict(self):
        data = {
            "name": "read_file",
            "display_name": "Read File",
            "abbreviation": "RD",
            "category": "read",
        }
        tool = ToolDefinition.from_dict(data)
        assert tool.name == "read_file"
        assert tool.category == ToolCategory.READ


class TestToolRegistry:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry.default()

    def test_default_tools_registered(self, registry: ToolRegistry):
        assert len(registry.list_tools()) == len(DEFAULT_TOOLS)

    def test_get_by_name(self, registry: ToolRegistry):
        tool = registry.get("grep")
        assert tool is not None
        assert tool.name == "grep"

    def test_get_by_alias(self, registry: ToolRegistry):
        tool = registry.get("rg")
        assert tool is not None
        assert tool.name == "grep"

    def test_get_nonexistent(self, registry: ToolRegistry):
        tool = registry.get("nonexistent_tool")
        assert tool is None

    def test_get_abbreviation(self, registry: ToolRegistry):
        abbr = registry.get_abbreviation("agentic_search")
        assert abbr == "AS"

    def test_get_abbreviation_fallback(self, registry: ToolRegistry):
        abbr = registry.get_abbreviation("unknown_tool")
        assert abbr == "UN"

    def test_get_category(self, registry: ToolRegistry):
        cat = registry.get_category("grep")
        assert cat == ToolCategory.SEARCH

    def test_list_by_category(self, registry: ToolRegistry):
        search_tools = registry.list_by_category(ToolCategory.SEARCH)
        assert len(search_tools) >= 2
        assert all(t.category == ToolCategory.SEARCH for t in search_tools)

    def test_register_custom_tool(self):
        registry = ToolRegistry(tools=[])
        custom = ToolDefinition(
            name="custom_tool",
            display_name="Custom",
            abbreviation="CT",
            category=ToolCategory.OTHER,
        )
        registry.register(custom)

        assert registry.get("custom_tool") is not None

    def test_to_dict_and_from_dict(self, registry: ToolRegistry):
        d = registry.to_dict()
        restored = ToolRegistry.from_dict(d)
        assert len(restored.list_tools()) == len(registry.list_tools())
