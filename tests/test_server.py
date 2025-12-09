from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server


class TestBuildServer:
    """Test build_server function."""

    def test_build_with_explicit_config(self, mock_config: RelaceConfig) -> None:
        """Should build server with provided config."""
        server = build_server(config=mock_config)
        assert server is not None
        assert server.name == "Relace Fast Apply MCP"

    def test_build_from_env(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should build server from environment variables."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")

        server = build_server()
        assert server is not None

    def test_build_fails_without_api_key(self, clean_env: None) -> None:
        """Should raise when RELACE_API_KEY is not set."""
        with pytest.raises(RuntimeError, match="RELACE_API_KEY"):
            build_server()


class TestServerToolRegistration:
    """Test that tools are properly registered."""

    @pytest.mark.asyncio
    async def test_relace_apply_file_registered(self, mock_config: RelaceConfig) -> None:
        """透過公開 API Client.list_tools() 驗證 tool 註冊。"""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "relace_apply_file" in tool_names


class TestServerToolExecution:
    """Test tool execution via server."""

    @pytest.mark.asyncio
    async def test_relace_apply_file_success(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should execute relace_apply_file tool successfully."""
        # Mock the RelaceClient.apply method
        with patch("relace_mcp.tools.RelaceClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.apply.return_value = successful_api_response
            mock_client_cls.return_value = mock_client

            server = build_server(config=mock_config)

            async with Client(server) as client:
                result = await client.call_tool(
                    "relace_apply_file",
                    {
                        "file_path": str(temp_source_file),
                        "edit_snippet": "// new code",
                        "instruction": "Add feature",
                    },
                )

                # FastMCP Client.call_tool returns deserialized data
                assert result is not None

    @pytest.mark.asyncio
    async def test_relace_apply_file_with_invalid_path(
        self, mock_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """Should return error for non-existent file."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            # Use call_tool_mcp to get raw MCP result with isError
            result = await client.call_tool_mcp(
                "relace_apply_file",
                {
                    "file_path": str(tmp_path / "nonexistent.py"),
                    "edit_snippet": "// edit",
                },
            )

            # Tool should return error
            assert result.isError is True

    @pytest.mark.asyncio
    async def test_relace_apply_file_empty_snippet(
        self, mock_config: RelaceConfig, temp_source_file: Path
    ) -> None:
        """Should return error for empty edit_snippet."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            result = await client.call_tool_mcp(
                "relace_apply_file",
                {
                    "file_path": str(temp_source_file),
                    "edit_snippet": "",
                },
            )

            assert result.isError is True


class TestServerIntegration:
    """Integration tests for server behavior."""

    @pytest.mark.asyncio
    async def test_server_lists_tools(self, mock_config: RelaceConfig) -> None:
        """Should list available tools."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()

            tool_names = [t.name for t in tools]
            assert "relace_apply_file" in tool_names

    @pytest.mark.asyncio
    async def test_tool_has_correct_schema(self, mock_config: RelaceConfig) -> None:
        """Should have correct input schema for relace_apply_file."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()

            relace_tool = next((t for t in tools if t.name == "relace_apply_file"), None)
            assert relace_tool is not None

            # 驗證必要參數
            schema = relace_tool.inputSchema
            assert "file_path" in schema.get("properties", {})
            assert "edit_snippet" in schema.get("properties", {})
            assert "instruction" in schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_full_apply_workflow(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        temp_log_file: Path,
        tmp_path: Path,
    ) -> None:
        """Test complete workflow: list tools -> call tool -> verify result."""
        config = RelaceConfig(
            api_key=mock_config.api_key,
            endpoint=mock_config.endpoint,
            model=mock_config.model,
            log_path=str(temp_log_file),
            timeout=mock_config.timeout,
            base_dir=str(tmp_path),
            strict_mode=False,
            max_retries=3,
            retry_base_delay=1.0,
        )

        merged_code = "def hello():\n    print('Modified!')\n"

        with patch("relace_mcp.tools.RelaceClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.apply.return_value = {
                "mergedCode": merged_code,
                "usage": {"total_tokens": 100},
            }
            mock_client_cls.return_value = mock_client

            server = build_server(config=config, run_health_check=False)

            async with Client(server) as client:
                # Step 1: List tools
                tools = await client.list_tools()
                assert len(tools) >= 1

                # Step 2: Call tool
                result = await client.call_tool(
                    "relace_apply_file",
                    {
                        "file_path": str(temp_source_file),
                        "edit_snippet": "def hello(): print('Modified!')",
                    },
                )

                assert result is not None

                # Step 3: Verify file was modified
                file_content = temp_source_file.read_text()
                assert file_content == merged_code
