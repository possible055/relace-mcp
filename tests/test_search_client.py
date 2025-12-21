from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients import RelaceSearchClient
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
            client = RelaceSearchClient(config)

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
            client = RelaceSearchClient(config)

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
        RelaceSearchClient(config)
