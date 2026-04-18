from pathlib import Path

import pytest
from fastmcp import Client

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

CORE_TOOLS = {"fast_apply", "agentic_search"}
CLOUD_TOOLS = {"cloud_sync", "cloud_search", "cloud_clear", "cloud_list"}
STATUS_TOOL = "index_status"


@pytest.fixture
def mock_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(api_key="rlc-contract-test", base_dir=str(tmp_path))


async def _list_tool_names(server) -> set[str]:
    async with Client(server) as client:
        tools = await client.list_tools()
        return {tool.name for tool in tools}


async def _list_resource_uris(server) -> set[str]:
    async with Client(server) as client:
        resources = await client.list_resources()
        return {str(resource.uri) for resource in resources}


class TestMCPToolExistence:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_core_tools_always_registered(self, mock_config: RelaceConfig) -> None:
        server = build_server(config=mock_config, run_health_check=False)
        assert CORE_TOOLS.issubset(await _list_tool_names(server))

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    @pytest.mark.parametrize(
        ("backend", "expected_cloud_tools", "expected_status_tool"),
        [
            ("relace", CLOUD_TOOLS, True),
            ("codanna", set(), True),
            ("chunkhound", set(), True),
            ("none", set(), False),
        ],
    )
    async def test_tool_visibility_matches_active_backend(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
        backend: str,
        expected_cloud_tools: set[str],
        expected_status_tool: bool,
    ) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", backend)
        server = build_server(config=mock_config, run_health_check=False)
        tool_names = await _list_tool_names(server)

        for tool in CLOUD_TOOLS:
            assert (tool in tool_names) is (tool in expected_cloud_tools)

        assert (STATUS_TOOL in tool_names) is expected_status_tool

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    @pytest.mark.parametrize("backend", ["relace", "codanna", "chunkhound", "none"])
    async def test_agentic_retrieval_visibility_depends_on_flag(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
        backend: str,
    ) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", backend)
        server_without = build_server(config=mock_config, run_health_check=False)
        assert "agentic_retrieval" not in await _list_tool_names(server_without)

        monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "1")
        server_with = build_server(config=mock_config, run_health_check=False)
        assert "agentic_retrieval" in await _list_tool_names(server_with)


class TestMCPToolSchemas:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_fast_apply_has_required_params(self, mock_config: RelaceConfig) -> None:
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            fast_apply = next((tool for tool in tools if tool.name == "fast_apply"), None)

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
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            search = next((tool for tool in tools if tool.name == "agentic_search"), None)

        assert search is not None
        schema = search.inputSchema
        props = schema.get("properties", {})
        assert "query" in props
        assert props["query"].get("type") == "string"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_all_tools_have_descriptions(self, mock_config: RelaceConfig) -> None:
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()

        for tool in tools:
            assert tool.description
            assert len(tool.description) > 10

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_all_tool_params_have_descriptions(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
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
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            fast_apply = next((tool for tool in tools if tool.name == "fast_apply"), None)

        assert fast_apply is not None
        annotations = fast_apply.annotations
        assert annotations is not None
        assert annotations.destructiveHint is True
        assert annotations.readOnlyHint is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_agentic_search_is_readonly(self, mock_config: RelaceConfig) -> None:
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            search = next((tool for tool in tools if tool.name == "agentic_search"), None)

        assert search is not None
        annotations = search.annotations
        assert annotations is not None
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_index_status_is_readonly(self, mock_config: RelaceConfig) -> None:
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            status_tool = next((tool for tool in tools if tool.name == STATUS_TOOL), None)

        assert status_tool is not None
        annotations = status_tool.annotations
        assert annotations is not None
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    @pytest.mark.parametrize(
        ("backend", "expected_read_only"),
        [("relace", True), ("codanna", False), ("chunkhound", False), ("none", True)],
    )
    async def test_agentic_retrieval_read_only_depends_on_backend(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
        backend: str,
        expected_read_only: bool,
    ) -> None:
        monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "1")
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", backend)
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            retrieval = next((tool for tool in tools if tool.name == "agentic_retrieval"), None)

        assert retrieval is not None
        annotations = retrieval.annotations
        assert annotations is not None
        assert annotations.readOnlyHint is expected_read_only
        assert annotations.destructiveHint is False


class TestMCPToolResponseContract:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_fast_apply_returns_structured_response(
        self, mock_config: RelaceConfig, tmp_path: Path
    ) -> None:
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
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            result = await client.call_tool(
                "fast_apply",
                {"path": str(tmp_path / "test.py"), "edit_snippet": ""},
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
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = [resource.uri for resource in resources]

            assert not any("tools_list" in str(uri) for uri in resource_uris)

            with pytest.raises(Exception, match="Unknown resource"):
                await client.read_resource("relace://tools_list")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    @pytest.mark.parametrize(
        ("backend", "expected_visible"),
        [("relace", True), ("codanna", False), ("chunkhound", False), ("none", False)],
    )
    async def test_cloud_status_resource_visibility_matches_backend(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
        backend: str,
        expected_visible: bool,
    ) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", backend)
        server = build_server(config=mock_config, run_health_check=False)
        resource_uris = await _list_resource_uris(server)
        assert ("relace://cloud/status" in resource_uris) is expected_visible

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_cloud_status_resource_can_be_read_when_enabled(
        self,
        mock_config: RelaceConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "relace")
        server = build_server(config=mock_config, run_health_check=False)

        async with Client(server) as client:
            result = await client.read_resource("relace://cloud/status")

        assert result is not None
        assert len(result) > 0
