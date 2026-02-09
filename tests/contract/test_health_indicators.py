from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

HEALTH_CHECK_INDICATORS = {
    "server_builds": "Server can be built with valid config",
    "tools_registered": "All expected tools are registered",
    "tool_schemas_valid": "All tool schemas have required fields",
    "tool_callable": "Tools can be invoked without crash",
    "response_format_ok": "Tool responses follow expected format",
}


@pytest.fixture
def health_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(api_key="rlc-health-check", base_dir=str(tmp_path))


class TestHealthIndicators:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_indicator_server_builds(self, health_config: RelaceConfig) -> None:
        """[HEALTH] Server can be built with valid configuration."""
        server = build_server(config=health_config, run_health_check=False)
        assert server is not None
        assert server.name == "Relace Fast Apply MCP"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_indicator_tools_registered(self, health_config: RelaceConfig) -> None:
        """[HEALTH] Core tools are properly registered."""
        server = build_server(config=health_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

            assert "fast_apply" in tool_names
            assert "agentic_search" in tool_names
            assert len(tools) >= 2

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_indicator_schemas_valid(self, health_config: RelaceConfig) -> None:
        """[HEALTH] All tool schemas have required type information."""
        server = build_server(config=health_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()

            for tool in tools:
                schema = tool.inputSchema
                assert schema is not None, f"Tool {tool.name} has no schema"
                assert "properties" in schema, f"Tool {tool.name} schema lacks properties"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_indicator_fast_apply_callable(
        self, health_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """[HEALTH] fast_apply can be invoked and returns valid response."""
        server = build_server(config=health_config, run_health_check=False)
        test_file = tmp_path / "health_check.py"

        async with Client(server) as client:
            result = await client.call_tool(
                "fast_apply",
                {"path": str(test_file), "edit_snippet": "# health check\nprint('ok')"},
            )

            assert result is not None
            content = result.structured_content
            assert content is not None
            assert content["status"] == "ok"
            assert test_file.exists()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_indicator_agentic_search_callable(
        self, health_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """[HEALTH] agentic_search can be invoked and returns valid response."""
        # Create a minimal file to search
        (tmp_path / "sample.py").write_text("def hello(): pass\n")

        # Define async function for side_effect to avoid coroutine warning
        async def mock_search(*args: object, **kwargs: object) -> dict[str, object]:
            return {"files": {}, "explanation": "test"}

        # Mock the LLM client to avoid real API calls
        with patch("relace_mcp.tools.SearchLLMClient") as mock_search_cls:
            mock_client = MagicMock()
            mock_client.search = mock_search
            mock_search_cls.return_value = mock_client

            server = build_server(config=health_config, run_health_check=False)

            async with Client(server) as client:
                result = await client.call_tool(
                    "agentic_search",
                    {"query": "find hello function"},
                )

                assert result is not None
                # Response can be structured_content or text based on outcome
                content = result.structured_content
                assert content is not None
                assert isinstance(content, dict)
                assert "files" in content or "explanation" in content

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_indicator_error_handling(
        self, health_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """[HEALTH] Tools handle errors gracefully (no crash, proper error response)."""
        server = build_server(config=health_config, run_health_check=False)

        async with Client(server) as client:
            # Test with invalid input (empty edit_snippet)
            result = await client.call_tool(
                "fast_apply",
                {"path": str(tmp_path / "test.py"), "edit_snippet": ""},
            )

            content = result.structured_content
            assert content is not None
            assert content["status"] == "error"
            assert "code" in content
            assert "message" in content


class TestFullHealthCheck:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_full_mcp_health_check(self, health_config: RelaceConfig, tmp_path: Path) -> None:
        """
        [FULL HEALTH CHECK] Comprehensive health check.

        This test covers all health indicators. Passing this test means the MCP server is fully operational:
        1. Server can be built
        2. All core tools are registered
        3. Tool schemas are valid
        4. Tools can be invoked
        5. Response format is correct
        """
        results: dict[str, bool] = {}

        # 1. Server builds
        try:
            server = build_server(config=health_config, run_health_check=False)
            results["server_builds"] = server is not None
        except Exception as e:
            results["server_builds"] = False
            pytest.fail(f"Server build failed: {e}")

        # 2-5. Tool checks
        async with Client(server) as client:
            # 2. Tools registered
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            results["tools_registered"] = (
                "fast_apply" in tool_names and "agentic_search" in tool_names
            )

            # 3. Schemas valid
            schemas_valid = all(t.inputSchema and "properties" in t.inputSchema for t in tools)
            results["schemas_valid"] = schemas_valid

            # 4. Tool callable (fast_apply)
            test_file = tmp_path / "full_health.py"
            call_result = await client.call_tool(
                "fast_apply",
                {"path": str(test_file), "edit_snippet": "print('health')"},
            )
            results["tool_callable"] = call_result is not None

            # 5. Response format
            content = call_result.structured_content
            results["response_format"] = (
                content is not None
                and isinstance(content, dict)
                and "status" in content
                and "message" in content
            )

        # Report
        all_passed = all(results.values())
        if not all_passed:
            failed = [k for k, v in results.items() if not v]
            pytest.fail(f"Health check failed: {failed}")

        assert all_passed, "All health indicators must pass"


class TestToolInvocationMatrix:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("clean_env")
    async def test_all_tools_invocable_with_minimal_input(
        self, health_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """Verify all registered tools can be invoked without crashing."""
        server = build_server(config=health_config, run_health_check=False)

        async with Client(server) as client:
            tools = await client.list_tools()

            invocation_results: dict[str, dict[str, Any]] = {}

            for tool in tools:
                try:
                    # Generate minimal valid args based on schema
                    args = _generate_minimal_args(tool.inputSchema, tmp_path)
                    result = await client.call_tool(tool.name, args)

                    invocation_results[tool.name] = {
                        "invocable": True,
                        "has_response": result is not None,
                    }
                except Exception as e:
                    invocation_results[tool.name] = {
                        "invocable": False,
                        "error": str(e),
                    }

            # All tools should be invocable
            failed_tools = [
                name for name, res in invocation_results.items() if not res.get("invocable", False)
            ]
            assert not failed_tools, f"Tools failed to invoke: {failed_tools}"


def _generate_minimal_args(schema: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    props = schema.get("properties", {})
    args: dict[str, Any] = {}

    for prop_name, prop_schema in props.items():
        prop_type = prop_schema.get("type", "string")

        if prop_name == "path":
            args[prop_name] = str(tmp_path / "test_file.py")
        elif prop_name == "edit_snippet":
            args[prop_name] = "# test content"
        elif prop_name == "query":
            args[prop_name] = "test query"
        elif prop_name in ("force", "mirror", "confirm"):
            args[prop_name] = False
        elif prop_name in ("reason", "instruction", "branch"):
            args[prop_name] = ""
        elif prop_type == "string":
            args[prop_name] = "test"
        elif prop_type == "boolean":
            args[prop_name] = False
        elif prop_type == "integer":
            args[prop_name] = 0

    return args
