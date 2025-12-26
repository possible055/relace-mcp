from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client

from relace_mcp.clients.apply import ApplyResponse
from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server


class TestBuildServer:
    """Test build_server function."""

    def test_build_with_explicit_config(self, mock_config: RelaceConfig) -> None:
        """Should build server with provided config."""
        server = build_server(config=mock_config)
        assert server is not None
        assert server.name == "Relace Fast Apply MCP"

    def test_build_from_env(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Should build server from environment variables."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))

        server = build_server()
        assert server is not None

    def test_build_fails_without_api_key(self, clean_env: None) -> None:
        """Should raise when RELACE_API_KEY is not set."""
        with pytest.raises(RuntimeError, match="RELACE_API_KEY"):
            build_server()


class TestServerToolRegistration:
    """Test that tools are properly registered."""

    @pytest.mark.asyncio
    async def test_fast_apply_registered(self, mock_config: RelaceConfig) -> None:
        """Verify tool registration via public API Client.list_tools()."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "fast_apply" in tool_names

    @pytest.mark.asyncio
    async def test_fast_search_registered(self, mock_config: RelaceConfig) -> None:
        """Verify fast_search registration via public API Client.list_tools()."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "fast_search" in tool_names


class TestServerToolExecution:
    """Test tool execution via server."""

    @pytest.mark.asyncio
    async def test_fast_apply_success(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should execute fast_apply tool successfully."""
        # Mock the ApplyLLMClient.apply method
        with patch("relace_mcp.tools.ApplyLLMClient") as mock_backend_cls:
            mock_backend = AsyncMock()
            mock_backend.apply.return_value = ApplyResponse(
                merged_code=successful_api_response["choices"][0]["message"]["content"],
                usage=successful_api_response.get("usage", {}),
            )
            mock_backend_cls.return_value = mock_backend

            server = build_server(config=mock_config)

            async with Client(server) as client:
                result = await client.call_tool(
                    "fast_apply",
                    {
                        "path": str(temp_source_file),
                        "edit_snippet": "// new code",
                        "instruction": "Add feature",
                    },
                )

                # FastMCP Client.call_tool returns deserialized data
                assert result is not None

    @pytest.mark.asyncio
    async def test_fast_apply_creates_new_file(
        self, mock_config: RelaceConfig, tmp_path: Path
    ) -> None:
        """Should create new file directly without calling API."""
        server = build_server(config=mock_config)
        new_file = tmp_path / "new_file.py"
        content = "print('hello')"

        async with Client(server) as client:
            result = await client.call_tool(
                "fast_apply",
                {
                    "path": str(new_file),
                    "edit_snippet": content,
                },
            )

            # FastMCP Client.call_tool returns CallToolResult with structured_content
            assert result.structured_content is not None
            assert result.structured_content["status"] == "ok"
            assert "Created" in result.structured_content["message"]
            assert new_file.exists()
            assert new_file.read_text() == content

    @pytest.mark.asyncio
    async def test_fast_apply_empty_snippet(
        self, mock_config: RelaceConfig, temp_source_file: Path
    ) -> None:
        """Should return error for empty edit_snippet."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            result = await client.call_tool_mcp(
                "fast_apply",
                {
                    "path": str(temp_source_file),
                    "edit_snippet": "",
                },
            )

            assert result.isError is False
            assert "INVALID_INPUT" in result.content[0].text


class TestServerIntegration:
    """Integration tests for server behavior."""

    @pytest.mark.asyncio
    async def test_fast_search_tool_has_correct_schema(self, mock_config: RelaceConfig) -> None:
        """Should have correct input schema for fast_search."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()

            search_tool = next((t for t in tools if t.name == "fast_search"), None)
            assert search_tool is not None

            schema = search_tool.inputSchema
            assert "query" in schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_tool_has_correct_schema(self, mock_config: RelaceConfig) -> None:
        """Should have correct input schema for fast_apply."""
        server = build_server(config=mock_config)

        async with Client(server) as client:
            tools = await client.list_tools()

            relace_tool = next((t for t in tools if t.name == "fast_apply"), None)
            assert relace_tool is not None

            # Verify required parameters
            schema = relace_tool.inputSchema
            assert "path" in schema.get("properties", {})
            assert "edit_snippet" in schema.get("properties", {})
            assert "instruction" in schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_full_apply_workflow(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Test complete workflow: list tools -> call tool -> verify result."""
        config = RelaceConfig(
            api_key=mock_config.api_key,
            base_dir=str(tmp_path),
        )

        # temp_source_file content: def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Goodbye')\n
        merged_code = "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Modified!')\n"

        with patch("relace_mcp.tools.ApplyLLMClient") as mock_backend_cls:
            mock_backend = AsyncMock()
            mock_backend.apply.return_value = ApplyResponse(
                merged_code=merged_code,
                usage={"total_tokens": 100},
            )
            mock_backend_cls.return_value = mock_backend

            server = build_server(config=config, run_health_check=False)

            async with Client(server) as client:
                # Step 1: List tools
                tools = await client.list_tools()
                assert len(tools) >= 1

                # Step 2: Call tool (edit_snippet contains anchor lines that exist in original file)
                result = await client.call_tool(
                    "fast_apply",
                    {
                        "path": str(temp_source_file),
                        "edit_snippet": "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Modified!')\n",
                    },
                )

                assert result is not None

                # Step 3: Verify file was modified
                file_content = temp_source_file.read_text()
                assert file_content == merged_code


class TestMain:
    """Test main() function with CLI arguments."""

    def test_main_stdio_mode(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """STDIO mode (default) calls server.run() without arguments."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp"])

        with patch("relace_mcp.server.build_server") as mock_build:
            mock_server = MagicMock()
            mock_build.return_value = mock_server

            main()

            mock_server.run.assert_called_once_with()

    def test_main_http_mode(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """HTTP mode calls server.run() with correct arguments via CLI."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "relace-mcp",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                "9000",
                "--path",
                "/api/mcp",
            ],
        )

        with patch("relace_mcp.server.build_server") as mock_build:
            mock_server = MagicMock()
            mock_build.return_value = mock_server

            main()

            mock_server.run.assert_called_once_with(
                transport="http",
                host="127.0.0.1",
                port=9000,
                path="/api/mcp",
            )

    def test_main_streamable_http_mode(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """streamable-http mode via -t short flag."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp", "-t", "streamable-http", "-p", "8080"])

        with patch("relace_mcp.server.build_server") as mock_build:
            mock_server = MagicMock()
            mock_build.return_value = mock_server

            main()

            mock_server.run.assert_called_once_with(
                transport="streamable-http",
                host="0.0.0.0",
                port=8080,
                path="/mcp",
            )

    def test_main_invalid_transport(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Invalid transport value is rejected by argparse."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp", "-t", "invalid"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 2  # argparse error exit code
