import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.relace_client import RelaceClient

# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def mock_config(tmp_path: Path) -> RelaceConfig:
    """Create a mock RelaceConfig without requiring environment variables."""
    return RelaceConfig(
        api_key="test-api-key-12345",
        endpoint="https://test.relace.run/v1/code/apply",
        model="relace-apply-3",
        log_path="/tmp/relace_test.log",
        timeout=30.0,
        base_dir=str(tmp_path),
        strict_mode=False,
        max_retries=3,
        retry_base_delay=1.0,
    )


@pytest.fixture
def mock_config_with_base_dir(tmp_path: Path) -> RelaceConfig:
    """Create a mock RelaceConfig with base_dir restriction enabled."""
    return RelaceConfig(
        api_key="test-api-key-12345",
        endpoint="https://test.relace.run/v1/code/apply",
        model="relace-apply-3",
        log_path=str(tmp_path / "relace.log"),
        timeout=30.0,
        base_dir=str(tmp_path),
        strict_mode=False,
        max_retries=3,
        retry_base_delay=1.0,
    )


# =============================================================================
# API Response Fixtures
# =============================================================================


@pytest.fixture
def successful_api_response() -> dict[str, Any]:
    """Standard successful Relace API response."""
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
    """Relace API error response payload."""
    return {
        "error": {
            "message": "Invalid API key",
            "type": "authentication_error",
        }
    }


# =============================================================================
# Mock HTTP Client Fixtures
# =============================================================================


@pytest.fixture
def mock_httpx_success(successful_api_response: dict[str, Any]):
    """Mock httpx.Client to return a successful response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
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
    """Mock httpx.Client to return an error response."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = '{"error": {"message": "Invalid API key"}}'

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_httpx_timeout():
    """Mock httpx.Client to raise TimeoutException."""
    import httpx

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_client):
        yield mock_client


# =============================================================================
# File System Fixtures
# =============================================================================


@pytest.fixture
def temp_source_file(tmp_path: Path) -> Path:
    """Create a temporary Python source file for testing."""
    source_file = tmp_path / "test_source.py"
    source_file.write_text(
        "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Goodbye')\n",
        encoding="utf-8",
    )
    return source_file


@pytest.fixture
def temp_large_file(tmp_path: Path) -> Path:
    """Create a temporary file that exceeds the size limit (>10MB)."""
    large_file = tmp_path / "large_file.py"
    # Create 11MB of content
    content = "x" * (11 * 1024 * 1024)
    large_file.write_text(content, encoding="utf-8")
    return large_file


@pytest.fixture
def temp_binary_file(tmp_path: Path) -> Path:
    """Create a temporary binary file (non-UTF-8)."""
    binary_file = tmp_path / "binary_file.bin"
    binary_file.write_bytes(b"\x80\x81\x82\x83\x84\x85")
    return binary_file


@pytest.fixture
def temp_log_file(tmp_path: Path) -> Path:
    """Create a temporary log file path."""
    return tmp_path / "test_relace.log"


# =============================================================================
# Client Fixtures
# =============================================================================


@pytest.fixture
def mock_relace_client(mock_config: RelaceConfig) -> RelaceClient:
    """Create a RelaceClient with mock config (requires mocked HTTP for tests)."""
    return RelaceClient(mock_config)


@pytest.fixture
def mock_client_with_response(
    mock_config: RelaceConfig, successful_api_response: dict[str, Any]
) -> Generator[RelaceClient, None, None]:
    """Create a RelaceClient that returns successful responses."""
    client = RelaceClient(mock_config)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = successful_api_response

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = mock_response

    with patch("relace_mcp.relace_client.httpx.Client", return_value=mock_http):
        yield client


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear all RELACE_* environment variables."""
    env_vars = [
        "RELACE_API_KEY",
        "RELACE_ENDPOINT",
        "RELACE_MODEL",
        "RELACE_LOG_PATH",
        "RELACE_TIMEOUT",
        "RELACE_BASE_DIR",
        "RELACE_STRICT_MODE",
        "RELACE_MAX_RETRIES",
        "RELACE_RETRY_BASE_DELAY",
        "RELACE_LOG_LEVEL",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def full_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """Set all RELACE_* environment variables to test values."""
    env = {
        "RELACE_API_KEY": "env-test-api-key",
        "RELACE_ENDPOINT": "https://env-test.relace.run/api",
        "RELACE_MODEL": "relace-apply-test",
        "RELACE_LOG_PATH": str(tmp_path / "env_test.log"),
        "RELACE_TIMEOUT": "45.0",
        "RELACE_BASE_DIR": str(tmp_path),
        "RELACE_STRICT_MODE": "false",
        "RELACE_MAX_RETRIES": "5",
        "RELACE_RETRY_BASE_DELAY": "2.0",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env
