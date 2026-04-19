from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from mcp.types import TextContent

from relace_mcp.clients.apply import ApplyResponse
from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server, check_health


@pytest.fixture(autouse=True)
def _neutralize_repo_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELACE_API_KEY", "")
    monkeypatch.setenv("MCP_BASE_DIR", "")
    monkeypatch.setenv("MCP_LOGGING", "off")
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
        """Server builds without RELACE_API_KEY on the default relace backend."""
        monkeypatch.setenv("RELACE_API_KEY", "")
        monkeypatch.setenv("MCP_BASE_DIR", "")
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "relace")
        monkeypatch.setenv("MCP_LOGGING", "off")
        server = build_server()
        assert server is not None

    @pytest.mark.usefixtures("clean_env")
    def test_health_reports_missing_relace_api_key_nonfatally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RELACE_API_KEY", "")
        monkeypatch.setenv("MCP_BASE_DIR", "")
        monkeypatch.setenv("MCP_RETRIEVAL_BACKEND", "relace")
        monkeypatch.setenv("MCP_LOGGING", "off")

        config = RelaceConfig.from_env()
        results = check_health(config)

        assert results["retrieval_backend"] == "relace: api_key_missing"


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
        with patch("relace_mcp.tools.mcp_status.shutil.which", return_value=None):
            server = build_server(config=mock_config)

            async with Client(server) as client:
                result = await client.call_tool(
                    "index_status",
                    {},
                )

                assert result.structured_content is not None
                payload = result.structured_content
                for key in ("trace_id", "base_dir", "base_dir_source", "active_backend", "backend"):
                    assert key in payload
                assert payload["active_backend"] == "relace"
                assert "freshness" in payload["backend"]
                assert "hints_usable" in payload["backend"]
                assert "background_monitor" in payload

    @pytest.mark.asyncio
    async def test_cloud_list_fails_fast_without_api_key(self, tmp_path: Path) -> None:
        config = RelaceConfig(api_key=None, base_dir=str(tmp_path))

        with patch("relace_mcp.clients.repo.RelaceRepoClient") as mock_repo_cls:
            server = build_server(config=config, run_health_check=False)

            async with Client(server) as client:
                result = await client.call_tool("cloud_list", {})

        payload = result.structured_content
        assert payload is not None
        assert payload["error"] == (
            "RELACE_API_KEY is required for Relace cloud tools. Set RELACE_API_KEY and retry."
        )
        assert payload["recommended_action"] == "Set RELACE_API_KEY and retry."
        assert payload["retryable"] is False
        mock_repo_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_agentic_retrieval_uses_optional_repo_client_when_api_key_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_SEARCH_RETRIEVAL", "1")
        config = RelaceConfig(api_key=None, base_dir=str(tmp_path))
        expected_result = {
            "explanation": "ok",
            "files": {},
            "turns_used": 1,
            "trace_id": "trace",
            "semantic_hints_used": 0,
            "hint_policy": "prefer-stale",
            "hints_index_freshness": "missing",
            "background_refresh_scheduled": False,
            "retrieval_task_completed": True,
            "retrieval_guidance_available": False,
            "retrieval_guidance_injected": False,
            "retrieval_guidance_turn": None,
            "warnings": ["Relace semantic retrieval unavailable. Proceeding without hints."],
        }

        with (
            patch("relace_mcp.tools._clients.ToolClients.get_search", return_value=MagicMock()),
            patch("relace_mcp.tools._clients.ToolClients.get_repo") as mock_get_repo,
            patch(
                "relace_mcp.tools.mcp_search.agentic_retrieval_logic",
                AsyncMock(return_value=expected_result),
            ) as mock_logic,
        ):
            server = build_server(config=config, run_health_check=False)

            async with Client(server) as client:
                result = await client.call_tool("agentic_retrieval", {"query": "find auth"})

        payload = result.structured_content
        assert payload == expected_result
        mock_get_repo.assert_not_called()
        assert mock_logic.await_args.args[0] is None

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
    def test_main_logs_runtime_from_built_server(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import sys

        from relace_mcp.server import main

        monkeypatch.setenv("RELACE_API_KEY", "rlc-test")
        monkeypatch.setenv("MCP_BASE_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["relace-mcp"])

        with (
            patch("relace_mcp.server.build_server") as mock_build,
            patch("relace_mcp.observability.log_event") as mock_log_event,
        ):
            mock_server = MagicMock()
            mock_server._relace_index_runtime = MagicMock(
                cloud_tools_enabled=False,
                active_backend="chunkhound",
            )
            mock_build.return_value = mock_server

            main()

        event = mock_log_event.call_args.args[0]
        assert event["cloud_tools_enabled"] is False
        assert event["mcp_retrieval_backend"] == "chunkhound"

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
