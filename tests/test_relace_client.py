from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from relace_mcp.clients import RelaceAPIError, RelaceClient, RelaceNetworkError, RelaceTimeoutError
from relace_mcp.config import RELACE_ENDPOINT, RELACE_MODEL, TIMEOUT_SECONDS, RelaceConfig


class TestRelaceClientApply:
    """Test RelaceClient.apply() method."""

    @pytest.mark.asyncio
    async def test_successful_apply(
        self,
        mock_config: RelaceConfig,
        mock_httpx_success: AsyncMock,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should return merged code on successful API call."""
        client = RelaceClient(mock_config)

        result = await client.apply(
            initial_code="def hello(): pass",
            edit_snippet="def hello(): print('hi')",
        )

        assert result == successful_api_response
        assert "mergedCode" in result
        assert "usage" in result

    @pytest.mark.asyncio
    async def test_apply_with_instruction(
        self, mock_config: RelaceConfig, mock_httpx_success: AsyncMock
    ) -> None:
        """Should include instruction in payload when provided."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        await client.apply(
            initial_code="code",
            edit_snippet="snippet",
            instruction="Add logging to the function",
        )

        # Verify payload contains instruction
        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["instruction"] == "Add logging to the function"

    @pytest.mark.asyncio
    async def test_apply_with_metadata(
        self, mock_config: RelaceConfig, mock_httpx_success: AsyncMock
    ) -> None:
        """Should include relace_metadata in payload when provided."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        metadata = {"source": "test", "file_path": "/test.py"}
        await client.apply(
            initial_code="code",
            edit_snippet="snippet",
            relace_metadata=metadata,
        )

        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["relace_metadata"] == metadata

    @pytest.mark.asyncio
    async def test_apply_without_optional_params(
        self, mock_config: RelaceConfig, mock_httpx_success: AsyncMock
    ) -> None:
        """Should not include optional params when not provided."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        await client.apply(initial_code="code", edit_snippet="snippet")

        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "instruction" not in payload
        assert "relace_metadata" not in payload


class TestRelaceClientPayload:
    """Test request payload construction."""

    @pytest.mark.asyncio
    async def test_payload_structure(
        self, mock_config: RelaceConfig, mock_httpx_success: AsyncMock
    ) -> None:
        """Should construct correct payload structure."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        await client.apply(initial_code="initial", edit_snippet="edit")

        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert payload["initial_code"] == "initial"
        assert payload["edit_snippet"] == "edit"
        assert payload["model"] == RELACE_MODEL
        assert payload["stream"] is False

    @pytest.mark.asyncio
    async def test_authorization_header(
        self, mock_config: RelaceConfig, mock_httpx_success: AsyncMock
    ) -> None:
        """Should include correct authorization header."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        await client.apply(initial_code="code", edit_snippet="snippet")

        call_args = mock_httpx_success.post.call_args
        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert headers["Authorization"] == f"Bearer {mock_config.api_key}"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_uses_constant_endpoint(
        self, mock_config: RelaceConfig, mock_httpx_success: AsyncMock
    ) -> None:
        """Should call the configured endpoint."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        await client.apply(initial_code="code", edit_snippet="snippet")

        call_args = mock_httpx_success.post.call_args
        endpoint = call_args.args[0] if call_args.args else call_args[0][0]
        assert endpoint == RELACE_ENDPOINT


class TestRelaceClientErrors:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_api_error_response(
        self, mock_config: RelaceConfig, mock_httpx_error: AsyncMock
    ) -> None:
        """Should raise RelaceAPIError on 401 response."""
        client = RelaceClient(mock_config)

        with pytest.raises(RelaceAPIError) as exc_info:
            await client.apply(initial_code="code", edit_snippet="snippet")

        # 401 error is not retryable
        assert exc_info.value.status_code == 401
        assert not exc_info.value.retryable

    @pytest.mark.asyncio
    async def test_timeout_error(
        self, mock_config: RelaceConfig, mock_httpx_timeout: AsyncMock
    ) -> None:
        """Should raise RelaceTimeoutError with helpful message on timeout."""
        client = RelaceClient(mock_config)

        with pytest.raises(RelaceTimeoutError, match="timed out"):
            await client.apply(initial_code="code", edit_snippet="snippet")

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_config: RelaceConfig) -> None:
        """Should raise RelaceNetworkError on connection failure."""
        client = RelaceClient(mock_config)

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RelaceNetworkError, match="Network error"):
                await client.apply(initial_code="code", edit_snippet="snippet")

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, mock_config: RelaceConfig) -> None:
        """Should raise RelaceAPIError on non-JSON response (server-side issue)."""
        client = RelaceClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.is_server_error = False
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "not json"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RelaceAPIError, match="non-JSON response") as exc_info:
                await client.apply(initial_code="code", edit_snippet="snippet")

            # Non-JSON response is retryable
            assert exc_info.value.retryable


class TestRelaceClientTimeout:
    """Test timeout configuration."""

    @pytest.mark.asyncio
    async def test_uses_constant_timeout(self, mock_config: RelaceConfig) -> None:
        """Should use timeout from config."""
        client = RelaceClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.return_value = {"mergedCode": "code", "usage": {}}

        with patch("relace_mcp.clients.relace.httpx.AsyncClient") as mock_client_class:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_instance

            await client.apply(initial_code="code", edit_snippet="snippet")

            # Verify AsyncClient was created with correct timeout
            mock_client_class.assert_called_once_with(timeout=TIMEOUT_SECONDS)


class TestRelaceClientRetry:
    """Test retry behavior for retryable errors."""

    @pytest.mark.asyncio
    async def test_rate_limit_respects_retry_after_header(self, mock_config: RelaceConfig) -> None:
        """Should use Retry-After header value for 429 responses."""
        client = RelaceClient(mock_config)
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.is_success = False
            mock_resp.text = '{"code": "rate_limit_exceeded", "message": "Too many requests"}'
            mock_resp.headers = {"retry-after": "2.5"}
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=mock_post)

        with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
            with patch("relace_mcp.clients.relace.asyncio.sleep") as mock_sleep:
                with pytest.raises(RelaceAPIError) as exc_info:
                    await client.apply(initial_code="code", edit_snippet="snippet")

                # Verify 429 error is retryable with retry_after
                assert exc_info.value.status_code == 429
                assert exc_info.value.retryable
                assert exc_info.value.retry_after == 2.5

                # Verify sleep used retry-after value (2.5 + jitter)
                from relace_mcp.config import MAX_RETRIES

                assert mock_sleep.call_count == MAX_RETRIES
                # First sleep should be based on retry-after=2.5
                first_delay = mock_sleep.call_args_list[0][0][0]
                assert 2.5 <= first_delay < 3.0  # 2.5 + jitter(0~0.5)

        assert call_count == MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_server_error_retries_with_backoff(self, mock_config: RelaceConfig) -> None:
        """Should retry 5xx errors with exponential backoff."""
        from relace_mcp.config import MAX_RETRIES, RETRY_BASE_DELAY

        client = RelaceClient(mock_config)
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.is_success = False
            mock_resp.text = '{"code": "internal_server_error", "message": "Server error"}'
            mock_resp.headers = {}
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=mock_post)

        with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
            with patch("relace_mcp.clients.relace.asyncio.sleep") as mock_sleep:
                with pytest.raises(RelaceAPIError) as exc_info:
                    await client.apply(initial_code="code", edit_snippet="snippet")

                # Verify 500 error is retryable
                assert exc_info.value.status_code == 500
                assert exc_info.value.retryable

                # Verify exponential backoff: delay = BASE * 2^attempt + jitter
                assert mock_sleep.call_count == MAX_RETRIES
                delays = [call[0][0] for call in mock_sleep.call_args_list]
                # First: BASE_DELAY * 2^0 + jitter
                assert RETRY_BASE_DELAY <= delays[0] < RETRY_BASE_DELAY + 0.5
                # Second: BASE_DELAY * 2^1 + jitter
                if len(delays) > 1:
                    assert RETRY_BASE_DELAY * 2 <= delays[1] < RETRY_BASE_DELAY * 2 + 0.5

        assert call_count == MAX_RETRIES + 1
