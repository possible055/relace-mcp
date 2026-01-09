from unittest.mock import MagicMock

import openai

from relace_mcp.backend.openai_backend import _should_retry


class TestShouldRetry:
    """Test _should_retry logic for tenacity retry decisions."""

    def _make_retry_state(self, exception: Exception | None) -> MagicMock:
        state = MagicMock()
        if exception is not None:
            state.outcome = MagicMock()
            state.outcome.exception.return_value = exception
        else:
            state.outcome = MagicMock()
            state.outcome.exception.return_value = None
        return state

    def test_no_exception_does_not_retry(self) -> None:
        state = self._make_retry_state(None)
        assert _should_retry(state) is False

    def test_rate_limit_error_retries(self) -> None:
        exc = openai.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is True

    def test_api_connection_error_retries(self) -> None:
        exc = openai.APIConnectionError(request=MagicMock())
        state = self._make_retry_state(exc)
        assert _should_retry(state) is True

    def test_api_timeout_error_retries(self) -> None:
        exc = openai.APITimeoutError(request=MagicMock())
        state = self._make_retry_state(exc)
        assert _should_retry(state) is True

    def test_5xx_status_error_retries(self) -> None:
        exc = openai.InternalServerError(
            message="Internal server error",
            response=MagicMock(status_code=500),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is True

    def test_502_status_error_retries(self) -> None:
        exc = openai.APIStatusError(
            message="Bad gateway",
            response=MagicMock(status_code=502),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is True

    def test_503_status_error_retries(self) -> None:
        exc = openai.APIStatusError(
            message="Service unavailable",
            response=MagicMock(status_code=503),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is True

    def test_4xx_status_error_does_not_retry(self) -> None:
        exc = openai.BadRequestError(
            message="Bad request",
            response=MagicMock(status_code=400),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is False

    def test_auth_error_does_not_retry(self) -> None:
        exc = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is False

    def test_permission_denied_does_not_retry(self) -> None:
        exc = openai.PermissionDeniedError(
            message="Permission denied",
            response=MagicMock(status_code=403),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is False

    def test_not_found_does_not_retry(self) -> None:
        exc = openai.NotFoundError(
            message="Not found",
            response=MagicMock(status_code=404),
            body=None,
        )
        state = self._make_retry_state(exc)
        assert _should_retry(state) is False

    def test_generic_exception_does_not_retry(self) -> None:
        exc = ValueError("Some other error")
        state = self._make_retry_state(exc)
        assert _should_retry(state) is False

    def test_none_outcome_does_not_retry(self) -> None:
        state = MagicMock()
        state.outcome = None
        assert _should_retry(state) is False
