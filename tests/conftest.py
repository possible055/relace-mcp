import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.relace_client import RelaceClient


@pytest.fixture
def mock_config(tmp_path: Path) -> RelaceConfig:
    return RelaceConfig(
        api_key="test-api-key-12345",
        base_dir=str(tmp_path),
    )


@pytest.fixture
def successful_api_response() -> dict[str, Any]:
    return {
        "mergedCode": "def hello():\n    print('Hello, World!')\n",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    }


@pytest.fixture
def api_error_response() -> dict[str, Any]:
    return {
        "error": {
            "message": "Invalid API key",
            "type": "authentication_error",
        }
    }


@pytest.fixture
def mock_httpx_success(successful_api_response: dict[str, Any]):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_server_error = False
    mock_response.json.return_value = successful_api_response
    mock_response.text = json.dumps(successful_api_response)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_httpx_error():
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.is_server_error = False
    mock_response.text = '{"error": {"message": "Invalid API key"}}'

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_httpx_timeout():
    import httpx

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def temp_source_file(tmp_path: Path) -> Path:
    source_file = tmp_path / "test_source.py"
    source_file.write_text(
        "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Goodbye')\n",
        encoding="utf-8",
    )
    return source_file


@pytest.fixture
def temp_large_file(tmp_path: Path) -> Path:
    large_file = tmp_path / "large_file.py"
    content = "x" * (11 * 1024 * 1024)
    large_file.write_text(content, encoding="utf-8")
    return large_file


@pytest.fixture
def temp_binary_file(tmp_path: Path) -> Path:
    binary_file = tmp_path / "binary_file.bin"
    binary_file.write_bytes(b"\x80\x81\x82\x83\x84\x85")
    return binary_file


@pytest.fixture
def mock_relace_client(mock_config: RelaceConfig) -> RelaceClient:
    return RelaceClient(mock_config)


@pytest.fixture
def mock_client_with_response(
    mock_config: RelaceConfig, successful_api_response: dict[str, Any]
) -> Generator[RelaceClient, None, None]:
    client = RelaceClient(mock_config)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_server_error = False
    mock_response.json.return_value = successful_api_response

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = mock_response

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_http):
        yield client


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ["RELACE_API_KEY", "RELACE_BASE_DIR"]:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def mock_log_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Auto-mock LOG_PATH for all tests to avoid writing to real log."""
    log_file = tmp_path / "test.log"
    with patch("relace_mcp.tools.LOG_PATH", log_file):
        yield log_file
