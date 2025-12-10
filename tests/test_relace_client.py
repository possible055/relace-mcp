from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from relace_mcp.clients import RelaceClient
from relace_mcp.config import RELACE_ENDPOINT, RELACE_MODEL, TIMEOUT_SECONDS, RelaceConfig


class TestRelaceClientApply:
    """Test RelaceClient.apply() method."""

    def test_successful_apply(
        self,
        mock_config: RelaceConfig,
        mock_httpx_success: MagicMock,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should return merged code on successful API call."""
        client = RelaceClient(mock_config)

        result = client.apply(
            initial_code="def hello(): pass",
            edit_snippet="def hello(): print('hi')",
        )

        assert result == successful_api_response
        assert "mergedCode" in result
        assert "usage" in result

    def test_apply_with_instruction(
        self, mock_config: RelaceConfig, mock_httpx_success: MagicMock
    ) -> None:
        """Should include instruction in payload when provided."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        client.apply(
            initial_code="code",
            edit_snippet="snippet",
            instruction="Add logging to the function",
        )

        # 驗證 payload 包含 instruction
        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["instruction"] == "Add logging to the function"

    def test_apply_with_metadata(
        self, mock_config: RelaceConfig, mock_httpx_success: MagicMock
    ) -> None:
        """Should include relace_metadata in payload when provided."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        metadata = {"source": "test", "file_path": "/test.py"}
        client.apply(
            initial_code="code",
            edit_snippet="snippet",
            relace_metadata=metadata,
        )

        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["relace_metadata"] == metadata

    def test_apply_without_optional_params(
        self, mock_config: RelaceConfig, mock_httpx_success: MagicMock
    ) -> None:
        """Should not include optional params when not provided."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        client.apply(initial_code="code", edit_snippet="snippet")

        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "instruction" not in payload
        assert "relace_metadata" not in payload


class TestRelaceClientPayload:
    """Test request payload construction."""

    def test_payload_structure(
        self, mock_config: RelaceConfig, mock_httpx_success: MagicMock
    ) -> None:
        """Should construct correct payload structure."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        client.apply(initial_code="initial", edit_snippet="edit")

        call_args = mock_httpx_success.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert payload["initial_code"] == "initial"
        assert payload["edit_snippet"] == "edit"
        assert payload["model"] == RELACE_MODEL
        assert payload["stream"] is False

    def test_authorization_header(
        self, mock_config: RelaceConfig, mock_httpx_success: MagicMock
    ) -> None:
        """Should include correct authorization header."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        client.apply(initial_code="code", edit_snippet="snippet")

        call_args = mock_httpx_success.post.call_args
        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert headers["Authorization"] == f"Bearer {mock_config.api_key}"
        assert headers["Content-Type"] == "application/json"

    def test_uses_constant_endpoint(
        self, mock_config: RelaceConfig, mock_httpx_success: MagicMock
    ) -> None:
        """Should call the configured endpoint."""
        client = RelaceClient(mock_config)
        mock_httpx_success.post.return_value.json.return_value = {
            "mergedCode": "code",
            "usage": {},
        }

        client.apply(initial_code="code", edit_snippet="snippet")

        call_args = mock_httpx_success.post.call_args
        endpoint = call_args.args[0] if call_args.args else call_args[0][0]
        assert endpoint == RELACE_ENDPOINT


class TestRelaceClientErrors:
    """Test error handling scenarios."""

    def test_api_error_response(
        self, mock_config: RelaceConfig, mock_httpx_error: MagicMock
    ) -> None:
        """Should raise RuntimeError on non-200 response."""
        client = RelaceClient(mock_config)

        with pytest.raises(RuntimeError, match="Relace API error.*status 401"):
            client.apply(initial_code="code", edit_snippet="snippet")

    def test_timeout_error(self, mock_config: RelaceConfig, mock_httpx_timeout: MagicMock) -> None:
        """Should raise RuntimeError with helpful message on timeout."""
        client = RelaceClient(mock_config)

        with pytest.raises(RuntimeError, match="timed out"):
            client.apply(initial_code="code", edit_snippet="snippet")

    def test_connection_error(self, mock_config: RelaceConfig) -> None:
        """Should raise RuntimeError on connection failure."""
        client = RelaceClient(mock_config)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        with patch("relace_mcp.clients.relace.httpx.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Failed to call Relace API"):
                client.apply(initial_code="code", edit_snippet="snippet")

    def test_invalid_json_response(self, mock_config: RelaceConfig) -> None:
        """Should raise RuntimeError on non-JSON response."""
        client = RelaceClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        with patch("relace_mcp.clients.relace.httpx.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="non-JSON response"):
                client.apply(initial_code="code", edit_snippet="snippet")


class TestRelaceClientTimeout:
    """Test timeout configuration."""

    def test_uses_constant_timeout(self, mock_config: RelaceConfig) -> None:
        """Should use timeout from config."""
        client = RelaceClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.return_value = {"mergedCode": "code", "usage": {}}

        with patch("relace_mcp.clients.relace.httpx.Client") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.post.return_value = mock_response
            mock_client_class.return_value = mock_instance

            client.apply(initial_code="code", edit_snippet="snippet")

            # 驗證 Client 建立時使用了正確的 timeout
            mock_client_class.assert_called_once_with(timeout=TIMEOUT_SECONDS)
