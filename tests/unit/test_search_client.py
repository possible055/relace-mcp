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


@pytest.mark.usefixtures("clean_env")
def test_relace_provider_uses_config_api_key_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)

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


@pytest.mark.usefixtures("clean_env")
def test_openai_provider_uses_search_api_key_and_compat_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openai")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://api.openai.com/v1")
    monkeypatch.setenv("SEARCH_MODEL", "gpt-4o")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-openai")

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

    # Check that OpenAI client was initialized with the provided API key and base_url
    call_kwargs = mock_openai.call_args.kwargs
    assert call_kwargs["api_key"] == "sk-openai"
    assert call_kwargs["base_url"] == "https://api.openai.com/v1"

    # Check model is default (relace-search falls through since no model override)
    create_kwargs = mock_client.chat.completions.create.call_args.kwargs

    # Check extra_body does NOT include Relace-specific params
    extra_body = create_kwargs.get("extra_body", {})
    assert "top_k" not in extra_body
    assert "repetition_penalty" not in extra_body


@pytest.mark.usefixtures("clean_env")
def test_openai_provider_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openai")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://api.openai.com/v1")
    monkeypatch.setenv("SEARCH_MODEL", "gpt-4o")

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="SEARCH_API_KEY"):
        SearchLLMClient(config)


@pytest.mark.usefixtures("clean_env")
def test_non_relace_provider_requires_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-or-test")
    monkeypatch.setenv("SEARCH_MODEL", "openai/gpt-4o")

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="SEARCH_ENDPOINT is required"):
        SearchLLMClient(config)


@pytest.mark.usefixtures("clean_env")
def test_openrouter_provider_uses_search_api_key_and_openai_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-or-test")

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


@pytest.mark.usefixtures("clean_env")
def test_openrouter_provider_endpoint_is_normalized(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-or-test")

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


@pytest.mark.usefixtures("clean_env")
def test_openrouter_provider_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SEARCH_MODEL", "openai/gpt-4o")

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="SEARCH_API_KEY"):
        SearchLLMClient(config)


@pytest.mark.usefixtures("clean_env")
def test_schema_error_retry_disables_parallel_and_strips_strict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "openrouter")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SEARCH_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-or-test")

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
            # Patch constant to disable parallel_tool_calls for this test
            with patch("relace_mcp.clients.search.SEARCH_PARALLEL_TOOL_CALLS", False):
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


@pytest.mark.usefixtures("clean_env")
def test_error_message_uses_provider_name_not_relace(tmp_path, monkeypatch) -> None:
    """Error messages should use actual provider name, not hardcoded 'Relace'."""
    monkeypatch.setenv("SEARCH_PROVIDER", "openai")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://api.openai.com/v1")
    monkeypatch.setenv("SEARCH_MODEL", "gpt-4o")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-test")

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
