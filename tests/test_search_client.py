import json
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients import RelaceSearchClient
from relace_mcp.config import RelaceConfig


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.is_success = True
    resp.text = json.dumps(payload)
    resp.headers = {}
    resp.json.return_value = payload
    return resp


def _mock_httpx_client(resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    client.post.return_value = resp
    return client


def test_relace_provider_uses_config_api_key_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RELACE_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    client = RelaceSearchClient(config)

    resp_payload = {"choices": [{"message": {"content": "ok"}}]}
    resp = _mock_response(resp_payload)
    mock_http = _mock_httpx_client(resp)

    with patch("relace_mcp.clients.search.httpx.Client", return_value=mock_http):
        result = client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], trace_id="t")

    assert result == resp_payload
    headers = mock_http.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer rlc-test"

    payload = mock_http.post.call_args.kwargs["json"]
    assert "top_k" in payload
    assert "repetition_penalty" in payload


def test_openai_provider_uses_openai_api_key_and_compat_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openai")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("RELACE_SEARCH_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    client = RelaceSearchClient(config)

    resp = _mock_response({"choices": [{"message": {"content": "ok"}}]})
    mock_http = _mock_httpx_client(resp)

    with patch("relace_mcp.clients.search.httpx.Client", return_value=mock_http):
        client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], trace_id="t")

    endpoint = mock_http.post.call_args.args[0]
    assert endpoint == "https://api.openai.com/v1/chat/completions"

    headers = mock_http.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-openai"

    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["model"] == "gpt-4o-mini"
    assert "top_k" not in payload
    assert "repetition_penalty" not in payload


def test_openai_provider_requires_openai_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RELACE_SEARCH_PROVIDER", "openai")
    monkeypatch.delenv("RELACE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("RELACE_SEARCH_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
    client = RelaceSearchClient(config)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], trace_id="t")
