from pathlib import Path

import pytest
from fastmcp import Client

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

CORE_TOOLS = ["fast_apply", "agentic_search"]
CLOUD_TOOLS = ["cloud_sync", "cloud_search", "cloud_clear", "cloud_list"]
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
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cloud tools must be visible when RELACE_CLOUD_TOOLS=true."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "1")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

            for tool in CLOUD_TOOLS:
                assert tool in tool_names, f"Cloud tool '{tool}' not registered"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_tools_absent_when_disabled(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cloud tools must be hidden when RELACE_CLOUD_TOOLS=false."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "0")
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

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_all_tool_params_have_descriptions(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All tool parameters must have non-empty descriptions in inputSchema."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "1")
        monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "1")
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "relace")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            for tool in tools:
                schema = tool.inputSchema or {}
                props = schema.get("properties", {})
                for param_name, param_schema in props.items():
                    assert isinstance(param_schema, dict), (
                        f"Tool '{tool.name}' param '{param_name}' schema is not an object"
                    )
                    desc = (param_schema.get("description") or "").strip()
                    assert desc, f"Tool '{tool.name}' param '{param_name}' has no description"


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

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_agentic_retrieval_is_not_readonly(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """agentic_retrieval may schedule background refreshes, so it is not read-only."""
        monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "1")
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "relace")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            retrieval = next((t for t in tools if t.name == "agentic_retrieval"), None)

            assert retrieval is not None
            annotations = retrieval.annotations
            assert annotations is not None
            assert annotations.readOnlyHint is False
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
    async def test_tools_list_resource_absent(self, mock_config: RelaceConfig) -> None:
        """Legacy tools_list resource should not be registered."""
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = [r.uri for r in resources]

            assert not any("tools_list" in str(uri) for uri in resource_uris)

            with pytest.raises(Exception, match="Unknown resource"):
                await client.read_resource("relace://tools_list")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_status_resource_visible_when_enabled(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cloud tools must be visible when RELACE_CLOUD_TOOLS=true."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "1")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]

            assert "relace://cloud/status" in resource_uris

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_status_resource_hidden_when_disabled(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cloud tools must be hidden when RELACE_CLOUD_TOOLS=false."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "0")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]

            assert "relace://cloud/status" not in resource_uris

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_status_resource_can_be_read_when_enabled(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cloud status resource must remain readable when cloud tools are enabled."""
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "1")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            result = await client.read_resource("relace://cloud/status")

            assert result is not None
            assert len(result) > 0
