from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.middleware.tracing import ToolTracingMiddleware
from relace_mcp.observability import context as observability_context


@pytest.fixture(autouse=True)
def clear_observability_context():
    """Clear observability context before each test."""
    observability_context.clear_context()
    yield
    observability_context.clear_context()


class TestToolTracingMiddleware:
    """Tests for ToolTracingMiddleware tool execution tracing."""

    @pytest.fixture
    def middleware(self) -> ToolTracingMiddleware:
        return ToolTracingMiddleware()

    @pytest.fixture
    def mock_call_next(self) -> AsyncMock:
        return AsyncMock(return_value={"status": "ok", "data": "test_result"})

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create a mock MiddlewareContext."""
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "test_tool"
        context.message.arguments = {"arg1": "value1", "arg2": "value2"}
        context.fastmcp_context = MagicMock()
        context.fastmcp_context.debug = AsyncMock()
        return context

    @pytest.mark.asyncio
    async def test_traces_tool_execution_success(
        self,
        middleware: ToolTracingMiddleware,
        mock_call_next: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Middleware should trace successful tool execution and record timing."""
        with (
            patch("relace_mcp.middleware.tracing.set_tool_context") as mock_set_tool_context,
            patch("relace_mcp.middleware.tracing.log_tool_start") as mock_log_tool_start,
            patch("relace_mcp.middleware.tracing.log_tool_complete") as mock_log_tool_complete,
            patch("relace_mcp.middleware.tracing.clear_context") as mock_clear_context,
        ):
            result = await middleware.on_call_tool(mock_context, mock_call_next)

            # Verify call chain
            mock_set_tool_context.assert_called_once_with("test_tool")
            mock_log_tool_start.assert_called_once_with(
                "test_tool", {"arg1": "value1", "arg2": "value2"}
            )
            mock_call_next.assert_awaited_once_with(mock_context)

            # Verify logging on success
            mock_log_tool_complete.assert_called_once()
            call_args = mock_log_tool_complete.call_args
            assert call_args[0][0] == "test_tool"  # tool_name
            assert isinstance(call_args[0][1], float)  # duration_ms
            assert call_args[0][2] == ["status", "data"]  # result_keys

            # Verify finally block calls clear_context
            mock_clear_context.assert_called_once()

            # Verify returned result
            assert result == {"status": "ok", "data": "test_result"}

    @pytest.mark.asyncio
    async def test_traces_tool_execution_with_empty_arguments(
        self,
        middleware: ToolTracingMiddleware,
        mock_call_next: AsyncMock,
    ) -> None:
        """Middleware should handle tool calls without arguments."""
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "tool_no_args"
        context.message.arguments = None
        context.fastmcp_context = None

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context") as mock_set_tool_context,
            patch("relace_mcp.middleware.tracing.log_tool_start") as mock_log_tool_start,
            patch("relace_mcp.middleware.tracing.log_tool_complete"),
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            await middleware.on_call_tool(context, mock_call_next)

            mock_set_tool_context.assert_called_once_with("tool_no_args")
            mock_log_tool_start.assert_called_once_with("tool_no_args", None)

    @pytest.mark.asyncio
    async def test_traces_tool_execution_error(
        self,
        middleware: ToolTracingMiddleware,
        mock_context: MagicMock,
    ) -> None:
        """Middleware should trace failed tool execution and record errors."""
        error = ValueError("Test error")
        mock_call_next_error = AsyncMock(side_effect=error)

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_error") as mock_log_tool_error,
            patch("relace_mcp.middleware.tracing.clear_context") as mock_clear_context,
            pytest.raises(ValueError, match="Test error"),
        ):
            await middleware.on_call_tool(mock_context, mock_call_next_error)

        # Verify logging on error (moved outside the with block)
        mock_log_tool_error.assert_called_once()
        call_args = mock_log_tool_error.call_args
        assert call_args[0][0] == "test_tool"  # tool_name
        assert isinstance(call_args[0][1], float)  # duration_ms
        assert "Test error" in call_args[0][2]  # error message
        assert call_args[0][3] == "ValueError"  # error_type

        # Verify clear_context is called even when exception is raised
        mock_clear_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_to_client_on_success(
        self,
        middleware: ToolTracingMiddleware,
        mock_call_next: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Success should send debug messages via MCP protocol."""
        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete"),
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            await middleware.on_call_tool(mock_context, mock_call_next)

            # Verify debug message sent to client
            mock_context.fastmcp_context.debug.assert_awaited_once()
            debug_message = mock_context.fastmcp_context.debug.call_args[0][0]
            assert "test_tool" in debug_message
            assert "ok" in debug_message

    @pytest.mark.asyncio
    async def test_logs_to_client_on_error(
        self,
        middleware: ToolTracingMiddleware,
        mock_context: MagicMock,
    ) -> None:
        """Failure should send error messages via MCP protocol."""
        error = RuntimeError("Critical failure")
        mock_call_next_error = AsyncMock(side_effect=error)

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_error"),
            patch("relace_mcp.middleware.tracing.clear_context"),
            pytest.raises(RuntimeError),
        ):
            await middleware.on_call_tool(mock_context, mock_call_next_error)

        # Verify error message sent to client (moved outside the with block)
        mock_context.fastmcp_context.debug.assert_awaited_once()
        debug_message = mock_context.fastmcp_context.debug.call_args[0][0]
        assert "test_tool" in debug_message
        assert "error" in debug_message
        assert "Critical failure" in debug_message

    @pytest.mark.asyncio
    async def test_handles_missing_fastmcp_context(
        self,
        middleware: ToolTracingMiddleware,
        mock_call_next: AsyncMock,
    ) -> None:
        """When fastmcp_context is None, it should work normally."""
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "test_tool"
        context.message.arguments = {}
        context.fastmcp_context = None

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete"),
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            # Should complete normally without raising exceptions
            result = await middleware.on_call_tool(context, mock_call_next)
            assert result == {"status": "ok", "data": "test_result"}

    @pytest.mark.asyncio
    async def test_handles_debug_logging_failure(
        self,
        middleware: ToolTracingMiddleware,
        mock_call_next: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """When debug logging fails, it should not affect the main flow."""
        mock_context.fastmcp_context.debug = AsyncMock(
            side_effect=Exception("Debug logging failed")
        )

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete"),
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            # Even with exceptions, the main flow should complete normally
            result = await middleware.on_call_tool(mock_context, mock_call_next)
            assert result == {"status": "ok", "data": "test_result"}

    @pytest.mark.asyncio
    async def test_result_keys_extraction_for_dict(
        self,
        middleware: ToolTracingMiddleware,
        mock_context: MagicMock,
    ) -> None:
        """Should correctly extract keys from dict results."""
        mock_call_next = AsyncMock(return_value={"key1": "value1", "key2": "value2"})

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete") as mock_log_tool_complete,
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            await middleware.on_call_tool(mock_context, mock_call_next)

            call_args = mock_log_tool_complete.call_args
            assert set(call_args[0][2]) == {"key1", "key2"}

    @pytest.mark.asyncio
    async def test_result_keys_none_for_non_dict(
        self,
        middleware: ToolTracingMiddleware,
        mock_context: MagicMock,
    ) -> None:
        """Non-dict results should have None as result_keys."""
        mock_call_next = AsyncMock(return_value="string_result")

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete") as mock_log_tool_complete,
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            await middleware.on_call_tool(mock_context, mock_call_next)

            call_args = mock_log_tool_complete.call_args
            assert call_args[0][2] is None


class TestToolTracingMiddlewareEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_handles_tool_with_unknown_name(self) -> None:
        """When message.name does not exist, should use 'unknown'."""
        middleware = ToolTracingMiddleware()
        context = MagicMock()
        context.message = MagicMock()
        # Simulate the case where name attribute does not exist
        delattr(context.message, "name")
        context.message.arguments = {}
        context.fastmcp_context = None
        mock_call_next = AsyncMock(return_value={})

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context") as mock_set_tool_context,
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete"),
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            await middleware.on_call_tool(context, mock_call_next)
            mock_set_tool_context.assert_called_once_with("unknown")

    @pytest.mark.asyncio
    async def test_timing_measurement(self) -> None:
        """Verify timing measurement is correct."""
        middleware = ToolTracingMiddleware()
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "slow_tool"
        context.message.arguments = {}
        context.fastmcp_context = None

        async def slow_call_next(context):
            import asyncio

            await asyncio.sleep(0.01)  # 10ms
            return {}

        with (
            patch("relace_mcp.middleware.tracing.set_tool_context"),
            patch("relace_mcp.middleware.tracing.log_tool_start"),
            patch("relace_mcp.middleware.tracing.log_tool_complete") as mock_log_tool_complete,
            patch("relace_mcp.middleware.tracing.clear_context"),
        ):
            await middleware.on_call_tool(context, slow_call_next)

            call_args = mock_log_tool_complete.call_args
            duration_ms = call_args[0][1]

            assert duration_ms >= 10.0

            assert duration_ms < 100.0
