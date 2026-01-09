from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients import ApplyLLMClient
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
        "choices": [
            {
                "message": {
                    "content": "def hello():\n    print('Hello, World!')\n",
                },
                "finish_reason": "stop",
            }
        ],
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
def temp_source_file(tmp_path: Path) -> Path:
    source_file = tmp_path / "test_source.py"
    content = "def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Goodbye')\n"
    # Use binary write to avoid Windows converting \n to \r\n
    source_file.write_bytes(content.encode("utf-8"))
    return source_file


@pytest.fixture
def temp_large_file(tmp_path: Path) -> Path:
    large_file = tmp_path / "large_file.py"
    content = "x" * (11 * 1024 * 1024)
    # Use binary write to avoid Windows newline conversion
    large_file.write_bytes(content.encode("utf-8"))
    return large_file


@pytest.fixture
def temp_binary_file(tmp_path: Path) -> Path:
    binary_file = tmp_path / "binary_file.bin"
    binary_file.write_bytes(b"\xfe\xff\x00\x80\xff\xfe\x81\x40")
    return binary_file


@pytest.fixture
def mock_apply_backend(
    mock_config: RelaceConfig,
) -> Generator[ApplyLLMClient, None, None]:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "def hello():\n    print('Hello, World!')\n"
    mock_response.choices[0].finish_reason = "stop"
    mock_response.model_dump.return_value = {
        "choices": [
            {
                "message": {"content": "def hello():\n    print('Hello, World!')\n"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.OpenAI"):
            yield ApplyLLMClient(mock_config)


@pytest.fixture
def mock_backend_with_response(
    mock_config: RelaceConfig, successful_api_response: dict[str, Any]
) -> Generator[ApplyLLMClient, None, None]:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = successful_api_response["choices"][0]["message"][
        "content"
    ]
    mock_response.choices[0].finish_reason = "stop"
    mock_response.model_dump.return_value = successful_api_response

    with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.OpenAI"):
            yield ApplyLLMClient(mock_config)


@pytest.fixture
def mock_backend() -> AsyncMock:
    return AsyncMock(spec=ApplyLLMClient)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear all environment variables that might affect tests."""
    prefixes = ["RELACE_", "SEARCH_", "APPLY_", "MCP_"]
    # Iterate through all variables starting with these prefixes and delete them
    import os

    for key in list(os.environ.keys()):
        for prefix in prefixes:
            if key.startswith(prefix):
                monkeypatch.delenv(key, raising=False)

    # Additionally clear common third-party API keys
    for var in ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "ANTHROPIC_API_KEY"]:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def mock_log_path(tmp_path: Path) -> Generator[Path, None, None]:
    log_file = tmp_path / "test.log"
    with (
        patch("relace_mcp.config.settings.MCP_LOGGING", True),
        patch("relace_mcp.config.settings.LOG_PATH", log_file),
    ):
        yield log_file
