import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import RelaceClient
from relace_mcp.config import RelaceConfig


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
    """Mock httpx.AsyncClient for successful API calls."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.is_server_error = False
    mock_response.json.return_value = successful_api_response
    mock_response.text = json.dumps(successful_api_response)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_httpx_error():
    """Mock httpx.AsyncClient for 401 error responses."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.is_success = False
    mock_response.is_server_error = False
    mock_response.text = '{"code": "invalid_api_key", "message": "Invalid API key"}'
    mock_response.headers = {}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_httpx_timeout():
    """Mock httpx.AsyncClient for timeout errors."""
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))

    with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_client):
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
    # Binary sequence that cannot be decoded by any text encoding (invalid UTF-8 + illegal GBK combo)
    binary_file.write_bytes(b"\xfe\xff\x00\x80\xff\xfe\x81\x40")
    return binary_file


@pytest.fixture
def mock_relace_client(mock_config: RelaceConfig) -> RelaceClient:
    return RelaceClient(mock_config)


@pytest.fixture
def mock_client_with_response(
    mock_config: RelaceConfig, successful_api_response: dict[str, Any]
) -> Generator[RelaceClient, None, None]:
    """Fixture providing a RelaceClient with mocked AsyncClient."""
    client = RelaceClient(mock_config)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.is_server_error = False
    mock_response.json.return_value = successful_api_response

    mock_http = AsyncMock()
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None
    mock_http.post = AsyncMock(return_value=mock_response)

    with patch("relace_mcp.clients.relace.httpx.AsyncClient", return_value=mock_http):
        yield client


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock RelaceClient with async apply method."""
    mock = AsyncMock(spec=RelaceClient)
    return mock


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ["RELACE_API_KEY", "RELACE_BASE_DIR"]:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def mock_log_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Auto-mock LOG_PATH and enable EXPERIMENTAL_LOGGING for all tests."""
    log_file = tmp_path / "test.log"
    with (
        patch("relace_mcp.tools.apply.logging.EXPERIMENTAL_LOGGING", True),
        patch("relace_mcp.tools.apply.logging.LOG_PATH", log_file),
    ):
        yield log_file
