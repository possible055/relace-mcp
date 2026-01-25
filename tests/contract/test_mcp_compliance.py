import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client
from mcp.types import TextResourceContents

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

CORE_TOOLS = ["fast_apply", "agentic_search"]
CLOUD_TOOLS = ["cloud_sync", "cloud_search", "cloud_clear", "cloud_list", "cloud_info"]
RETRIEVAL_TOOLS = ["agentic_retrieval"]


@pytest.fixture
def mock_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(api_key="rlc-contract-test", base_dir=str(tmp_path))


class TestMCPToolExistence:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_core_tools_always_registered(self, mock_config: RelaceConfig) -> None:
        """Core tools (fast_apply, agentic_search) must always be present."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

            for tool in CORE_TOOLS:
                assert tool in tool_names, f"Core tool '{tool}' not registered"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_tools_conditional_on_flag(
        self, mock_config: RelaceConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cloud tools only registered when RELACE_CLOUD_TOOLS=true."""
        with patch("relace_mcp.tools.RELACE_CLOUD_TOOLS", True):
            server = build_server(config=mock_config, run_health_check=False)

            async with Client(server) as client:
                tools = await client.list_tools()
                tool_names = {t.name for t in tools}

                for tool in CLOUD_TOOLS:
                    assert tool in tool_names, f"Cloud tool '{tool}' not registered"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_tools_absent_when_disabled(self, mock_config: RelaceConfig) -> None:
        """Cloud tools must NOT be registered when RELACE_CLOUD_TOOLS=false."""
        with patch("relace_mcp.tools.RELACE_CLOUD_TOOLS", False):
            server = build_server(config=mock_config, run_health_check=False)

            async with Client(server) as client:
                tools = await client.list_tools()
                tool_names = {t.name for t in tools}

                for tool in CLOUD_TOOLS:
                    assert tool not in tool_names, f"Cloud tool '{tool}' should NOT be registered"


class TestMCPToolSchemas:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_fast_apply_has_required_params(self, mock_config: RelaceConfig) -> None:
        """fast_apply must have path, edit_snippet, instruction parameters."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            fast_apply = next((t for t in tools if t.name == "fast_apply"), None)

            assert fast_apply is not None
            schema = fast_apply.inputSchema
            props = schema.get("properties", {})

            assert "path" in props
            assert "edit_snippet" in props
            assert "instruction" in props
            assert props["path"].get("type") == "string"
            assert props["edit_snippet"].get("type") == "string"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_agentic_search_has_query_param(self, mock_config: RelaceConfig) -> None:
        """agentic_search must have query parameter."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            search = next((t for t in tools if t.name == "agentic_search"), None)

            assert search is not None
            schema = search.inputSchema
            props = schema.get("properties", {})

            assert "query" in props
            assert props["query"].get("type") == "string"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_all_tools_have_descriptions(self, mock_config: RelaceConfig) -> None:
        """All tools must have non-empty descriptions."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()

            for tool in tools:
                assert tool.description, f"Tool '{tool.name}' has no description"
                assert len(tool.description) > 10, f"Tool '{tool.name}' description too short"


class TestMCPToolAnnotations:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_fast_apply_is_destructive(self, mock_config: RelaceConfig) -> None:
        """fast_apply must be marked as destructive (modifies files)."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            fast_apply = next((t for t in tools if t.name == "fast_apply"), None)

            assert fast_apply is not None
            annotations = fast_apply.annotations
            assert annotations is not None
            assert annotations.destructiveHint is True
            assert annotations.readOnlyHint is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_agentic_search_is_readonly(self, mock_config: RelaceConfig) -> None:
        """agentic_search must be marked as read-only."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            search = next((t for t in tools if t.name == "agentic_search"), None)

            assert search is not None
            annotations = search.annotations
            assert annotations is not None
            assert annotations.readOnlyHint is True
            assert annotations.destructiveHint is False


class TestMCPToolResponseContract:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_fast_apply_returns_structured_response(
        self, mock_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """fast_apply must return dict with status, message, path keys."""
        server = build_server(config=mock_config, run_health_check=False)
        new_file = tmp_path / "new.py"

        async with Client(server) as client:
            result = await client.call_tool(
                "fast_apply",
                {"path": str(new_file), "edit_snippet": "print('hello')"},
            )

            content = result.structured_content
            assert content is not None
            assert isinstance(content, dict)
            assert "status" in content
            assert content["status"] in ("ok", "error")
            assert "message" in content
            assert "path" in content

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_fast_apply_error_returns_code(
        self, mock_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """fast_apply error response must include code field."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            result = await client.call_tool(
                "fast_apply",
                {"path": str(tmp_path / "test.py"), "edit_snippet": ""},  # empty = error
            )

            content = result.structured_content
            assert content is not None
            assert content["status"] == "error"
            assert "code" in content
            assert content["code"] == "INVALID_INPUT"


class TestMCPResourceExistence:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_tools_list_resource_exists(self, mock_config: RelaceConfig) -> None:
        """relace://tools_list resource must be registered."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = [r.uri for r in resources]

            assert any("tools_list" in str(uri) for uri in resource_uris)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_tools_list_returns_valid_structure(self, mock_config: RelaceConfig) -> None:
        """relace://tools_list must return list of tool info dicts."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            result = await client.read_resource("relace://tools_list")
            # FastMCP returns TextContent list
            assert result is not None
            assert len(result) > 0
            first_content = result[0]
            # Handle both TextResourceContents and BlobResourceContents
            if isinstance(first_content, TextResourceContents):
                content_text = first_content.text
            else:
                # BlobResourceContents has blob attribute
                content_text = first_content.blob.decode("utf-8")  # type: ignore[union-attr]

            tools_list = json.loads(content_text)
            assert isinstance(tools_list, list)
            assert len(tools_list) >= 2  # at least core tools

            for tool_info in tools_list:
                assert "id" in tool_info
                assert "name" in tool_info
                assert "enabled" in tool_info
