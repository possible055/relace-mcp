import json
from unittest.mock import MagicMock

import pytest

from relace_mcp.clients import RelaceAPIError
from relace_mcp.clients.exceptions import raise_for_status


def test_raise_for_status_parses_openai_error_format() -> None:
    resp = MagicMock()
    resp.status_code = 401
    resp.is_success = False
    resp.headers = {}
    resp.text = json.dumps(
        {
            "error": {
                "message": "Incorrect API key provided",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        }
    )

    with pytest.raises(RelaceAPIError) as exc_info:
        raise_for_status(resp)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "invalid_api_key"
    assert "Incorrect API key" in exc_info.value.message
    assert exc_info.value.retryable is False
