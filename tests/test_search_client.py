from unittest.mock import MagicMock, patch

import openai
import pytest

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig


def _mock_chat_response(content: str = "ok") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = "stop"
    response.model_dump.return_value = {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }
    return response


def test_relace_provider_uses_config_api_key_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RELACE_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    mock_response = _mock_chat_response()

    with patch("relace_mcp.backend.openai_backend.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI"):
            config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            client = SearchLLMClient(config)

            result = client.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                trace_id="t",
            )

    assert result["choices"][0]["message"]["content"] == "ok"

    # Check that OpenAI client was initialized with Relace API key
    mock_openai.assert_called_once()
    call_kwargs = mock_openai.call_args.kwargs
    assert call_kwargs["api_key"] == "rlc-test"

    # Check extra_body includes Relace-specific params
    create_kwargs = mock_client.chat.completions.create.call_args.kwargs
    extra_body = create_kwargs.get("extra_body", {})
    assert extra_body.get("top_k") == 100
    assert extra_body.get("repetition_penalty") == 1.0


def test_openai_provider_uses_openai_api_key_and_compat_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openai")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("RELACE_SEARCH_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    mock_response = _mock_chat_response()

    with patch("relace_mcp.backend.openai_backend.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI"):
            config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            client = SearchLLMClient(config)

            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                trace_id="t",
            )

    # Check that OpenAI client was initialized with OpenAI API key and base_url
    call_kwargs = mock_openai.call_args.kwargs
    assert call_kwargs["api_key"] == "sk-openai"
    assert call_kwargs["base_url"] == "https://api.openai.com/v1"

    # Check model is gpt-4o (default for openai provider in search)
    create_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert create_kwargs["model"] == "gpt-4o"

    # Check extra_body does NOT include Relace-specific params
    extra_body = create_kwargs.get("extra_body", {})
    assert "top_k" not in extra_body
    assert "repetition_penalty" not in extra_body


def test_openai_provider_requires_openai_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openai")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("RELACE_SEARCH_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        SearchLLMClient(config)


def test_openrouter_provider_uses_openrouter_api_key_and_openai_payload(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openrouter")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.setenv("RELACE_SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    mock_response = _mock_chat_response()

    with patch("relace_mcp.backend.openai_backend.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI"):
            config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            client = SearchLLMClient(config)
            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                trace_id="t",
            )

    call_kwargs = mock_openai.call_args.kwargs
    assert call_kwargs["api_key"] == "sk-or-test"
    assert call_kwargs["base_url"] == "https://openrouter.ai/api/v1"

    create_kwargs = mock_client.chat.completions.create.call_args.kwargs
    extra_body = create_kwargs.get("extra_body", {})
    assert "top_k" not in extra_body
    assert "repetition_penalty" not in extra_body


def test_openrouter_provider_endpoint_is_normalized(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("RELACE_SEARCH_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("RELACE_SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    mock_response = _mock_chat_response()

    with patch("relace_mcp.backend.openai_backend.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI"):
            config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            client = SearchLLMClient(config)
            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                trace_id="t",
            )

    call_kwargs = mock_openai.call_args.kwargs
    assert call_kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_openrouter_provider_requires_provider_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("RELACE_SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.delenv("RELACE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("RELACE_SEARCH_API_KEY_ENV", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="No API key found.*RELACE_SEARCH_API_KEY"):
        SearchLLMClient(config)


def test_schema_error_retry_disables_parallel_and_strips_strict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openrouter")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.setenv("RELACE_SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    # Disable parallel_tool_calls to test strict-only retry path
    monkeypatch.setenv("RELACE_SEARCH_PARALLEL_TOOL_CALLS", "0")

    tool_with_strict = [
        {"type": "function", "function": {"name": "report_back", "strict": True, "parameters": {}}}
    ]
    mock_response = _mock_chat_response()

    def _create_side_effect(**kwargs):
        extra_body = kwargs.get("extra_body", {})
        tools = extra_body.get("tools", [])
        has_strict = any("strict" in t.get("function", {}) for t in tools if isinstance(t, dict))
        if has_strict:
            raise openai.BadRequestError(
                message="schema rejected",
                response=MagicMock(status_code=400),
                body=None,
            )
        return mock_response

    with patch("relace_mcp.backend.openai_backend.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _create_side_effect
        mock_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI"):
            config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            client = SearchLLMClient(config)

            # First call triggers compatibility retry (strict=true rejected -> retry without strict).
            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=tool_with_strict,
                trace_id="t1",
            )

            # Second call should not send strict (already stripped after first retry).
            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=tool_with_strict,
                trace_id="t2",
            )

    # First call: 1 fail (strict) + 1 retry (stripped) = 2 calls
    # Second call: 1 success (already stripped) = 1 call
    # Total: 3 calls
    assert mock_client.chat.completions.create.call_count == 3
    second_call_kwargs = mock_client.chat.completions.create.call_args_list[-1].kwargs
    extra_body = second_call_kwargs.get("extra_body", {})
    assert "parallel_tool_calls" not in extra_body
    assert all("strict" not in t.get("function", {}) for t in extra_body.get("tools", []))


def test_error_message_uses_provider_name_not_relace(tmp_path, monkeypatch) -> None:
    """Error messages should use actual provider name, not hardcoded 'Relace'."""
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openai")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("RELACE_SEARCH_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with patch("relace_mcp.backend.openai_backend.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        mock_openai.return_value = mock_client

        with patch("relace_mcp.backend.openai_backend.AsyncOpenAI"):
            config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            client = SearchLLMClient(config)

            with pytest.raises(RuntimeError) as exc_info:
                client.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                    trace_id="t",
                )

    # Verify error message uses "Openai" not "Relace"
    assert "Openai" in str(exc_info.value)
    assert "Relace" not in str(exc_info.value)
