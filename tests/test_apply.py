from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from relace_mcp.clients import ApplyLLMClient
from relace_mcp.clients.apply import ApplyRequest
from relace_mcp.config import RelaceConfig


def _mock_chat_response(content: str, usage: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = "stop"
    response.usage = MagicMock()
    response.usage.prompt_tokens = (usage or {}).get("prompt_tokens", 100)
    response.usage.completion_tokens = (usage or {}).get("completion_tokens", 50)
    response.usage.total_tokens = (usage or {}).get("total_tokens", 150)
    response.model_dump.return_value = {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    return response


class TestApplyLLMClientApply:
    @pytest.mark.asyncio
    async def test_successful_apply(self, mock_config: RelaceConfig) -> None:
        mock_response = _mock_chat_response(
            "def hello():\n    print('Hello, World!')\n",
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(
                    initial_code="def hello(): pass",
                    edit_snippet="def hello(): print('hi')",
                )

                response = await backend.apply(request)

        assert response.merged_code == "def hello():\n    print('Hello, World!')\n"
        assert response.usage["prompt_tokens"] == 100

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fences(self, mock_config: RelaceConfig) -> None:
        mock_response = _mock_chat_response(
            "```python\ndef hello():\n    print('Hello, World!')\n```\n"
        )

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(
                    initial_code="def hello(): pass",
                    edit_snippet="def hello(): print('hi')",
                )
                response = await backend.apply(request)

        assert response.merged_code == "def hello():\n    print('Hello, World!')\n"


class TestApplyLLMClientPayload:
    @pytest.mark.asyncio
    async def test_payload_structure(self, mock_config: RelaceConfig) -> None:
        mock_response = _mock_chat_response("code")

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(initial_code="initial", edit_snippet="edit")

                await backend.apply(request)

                call_kwargs = mock_client.chat.completions.create.call_args.kwargs
                assert call_kwargs["model"] == "auto"
                assert len(call_kwargs["messages"]) == 1
                assert call_kwargs["messages"][0]["role"] == "user"
                assert "<code>initial</code>" in call_kwargs["messages"][0]["content"]
                assert "<update>edit</update>" in call_kwargs["messages"][0]["content"]
                assert call_kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_payload_includes_instruction(self, mock_config: RelaceConfig) -> None:
        mock_response = _mock_chat_response("code")

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(
                    initial_code="initial",
                    edit_snippet="edit",
                    instruction="Prefer minimal diff; keep function signature unchanged.",
                )

                await backend.apply(request)

                call_kwargs = mock_client.chat.completions.create.call_args.kwargs
                content = call_kwargs["messages"][0]["content"]
                assert (
                    "<instruction>Prefer minimal diff; keep function signature unchanged.</instruction>"
                    in content
                )


class TestApplyLLMClientErrors:
    @pytest.mark.asyncio
    async def test_api_error_response(self, mock_config: RelaceConfig) -> None:
        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.AuthenticationError(
                    message="Invalid API key",
                    response=MagicMock(status_code=401),
                    body=None,
                )
            )
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(initial_code="code", edit_snippet="snippet")

                with pytest.raises(openai.AuthenticationError):
                    await backend.apply(request)

    @pytest.mark.asyncio
    async def test_timeout_error(self, mock_config: RelaceConfig) -> None:
        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.APITimeoutError(request=MagicMock())
            )
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(initial_code="code", edit_snippet="snippet")

                with pytest.raises(openai.APITimeoutError):
                    await backend.apply(request)

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_config: RelaceConfig) -> None:
        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.APIConnectionError(request=MagicMock())
            )
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(initial_code="code", edit_snippet="snippet")

                with pytest.raises(openai.APIConnectionError):
                    await backend.apply(request)


class TestApplyLLMClientRetry:
    @pytest.mark.asyncio
    async def test_rate_limit_retries(self, mock_config: RelaceConfig) -> None:
        from relace_mcp.config.settings import MAX_RETRIES

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            raise openai.RateLimitError(
                message="Too many requests",
                response=MagicMock(status_code=429),
                body=None,
            )

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = mock_create
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(initial_code="code", edit_snippet="snippet")

                with pytest.raises(openai.RateLimitError):
                    await backend.apply(request)

        assert call_count == MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_server_error_retries(self, mock_config: RelaceConfig) -> None:
        from relace_mcp.config.settings import MAX_RETRIES

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            raise openai.InternalServerError(
                message="Server error",
                response=MagicMock(status_code=500),
                body=None,
            )

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI") as mock_async_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = mock_create
            mock_async_openai.return_value = mock_client

            with patch("relace_mcp.backend.openai_backend.OpenAI"):
                backend = ApplyLLMClient(mock_config)
                request = ApplyRequest(initial_code="code", edit_snippet="snippet")

                with pytest.raises(openai.InternalServerError):
                    await backend.apply(request)

        assert call_count == MAX_RETRIES + 1
