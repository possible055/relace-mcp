from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from mcp.types import TextContent

from relace_mcp.clients.apply import ApplyResponse
from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server


@pytest.fixture(autouse=True)
def _neutralize_repo_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELACE_API_KEY", "")
    monkeypatch.setenv("MCP_BASE_DIR", "")
    monkeypatch.setenv("MCP_LOGGING", "off")
    monkeypatch.setenv("RELACE_CLOUD_TOOLS", "0")
    monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "0")
    monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "relace")


class TestBuildServer:
    """Test build_server function."""

    def test_build_with_explicit_config(self, mock_config: RelaceConfig) -> None:
        """Should build server with provided config."""
        server = build_server(config=mock_config)
        assert server is not None
        assert server.name == "Relace Fast Apply MCP"

    @pytest.mark.usefixtures("clean_env")
    def test_build_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Should build server from environment variables."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("MCP_BASE_DIR", str(tmp_path))
        monkeypatch.setenv("MCP_LOGGING", "off")

        server = build_server()
        assert server is not None

    @pytest.mark.usefixtures("clean_env")
    def test_build_succeeds_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Server builds without RELACE_API_KEY; error deferred to first tool call."""
        monkeypatch.setenv("RELACE_API_KEY", "")
        monkeypatch.setenv("MCP_BASE_DIR", "")
        monkeypatch.setenv("RELACE_CLOUD_TOOLS", "0")
        monkeypatch.setenv("MCP_LOGGING", "off")
        server = build_server()
        assert server is not None


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
        with patch("relace_mcp.clients.apply.ApplyLLMClient") as mock_backend_cls:
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

                assert result is not None

    @pytest.mark.asyncio
    async def test_index_status_success(self, mock_config: RelaceConfig) -> None:
        """Should execute index_status tool successfully."""
        with (
            patch("relace_mcp.tools.register._should_register_index_status", return_value=True),
            patch("relace_mcp.tools.mcp_status.shutil.which", return_value=None),
        ):
            server = build_server(config=mock_config)

            async with Client(server) as client:
                result = await client.call_tool(
                    "index_status",
                    {},
                )

                assert result.structured_content is not None
                payload = result.structured_content
                for key in ("trace_id", "base_dir", "relace", "codanna", "chunkhound"):
                    assert key in payload
                assert "freshness" in payload["relace"]
                assert "hints_usable" in payload["relace"]
                assert "freshness" in payload["codanna"]
                assert "hints_usable" in payload["codanna"]

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
            assert result.content
            first = result.content[0]
            assert isinstance(first, TextContent)
            assert "INVALID_INPUT" in first.text

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

        merged_code = "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Modified!')\n"

        with patch("relace_mcp.clients.apply.ApplyLLMClient") as mock_backend_cls:
            mock_backend = AsyncMock()
            mock_backend.apply.return_value = ApplyResponse(
                merged_code=merged_code,
                usage={"total_tokens": 100},
            )
            mock_backend_cls.return_value = mock_backend

            server = build_server(config=config, run_health_check=False)

            async with Client(server) as client:
                tools = await client.list_tools()
                assert len(tools) >= 1

                result = await client.call_tool(
                    "fast_apply",
                    {
                        "path": str(temp_source_file),
                        "edit_snippet": "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Modified!')\n",
                    },
                )

                assert result is not None
                assert temp_source_file.read_text() == merged_code


class TestMain:
    """Test main() function with CLI arguments."""

    @pytest.mark.usefixtures("clean_env")
    def test_main_stdio_mode(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """STDIO mode (default) calls server.run() without arguments."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("MCP_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp"])

        with patch("relace_mcp.server.build_server") as mock_build:
            mock_server = MagicMock()
            mock_build.return_value = mock_server

            main()

            mock_build.assert_called_once()
            assert mock_build.call_args.kwargs["initialize_runtime"] is False
            mock_server.run.assert_called_once_with(show_banner=False)

    @pytest.mark.usefixtures("clean_env")
    def test_main_http_mode(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """HTTP mode calls server.run() with correct arguments via CLI."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("MCP_BASE_DIR", str(tmp_path))
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
                show_banner=False,
            )

    @pytest.mark.usefixtures("clean_env")
    def test_main_streamable_http_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """streamable-http mode via -t short flag."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("MCP_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp", "-t", "streamable-http", "-p", "8080"])

        with patch("relace_mcp.server.build_server") as mock_build:
            mock_server = MagicMock()
            mock_build.return_value = mock_server

            main()

            mock_server.run.assert_called_once_with(
                transport="streamable-http",
                host="127.0.0.1",
                port=8080,
                path="/mcp",
                show_banner=False,
            )

    @pytest.mark.usefixtures("clean_env")
    def test_main_invalid_transport(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Invalid transport value is rejected by argparse."""
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("MCP_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp", "-t", "invalid"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 2  # argparse error exit code
