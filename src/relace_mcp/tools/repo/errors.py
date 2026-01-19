from typing import Any

import httpx

from ...clients.exceptions import RelaceAPIError


def build_cloud_error_details(exc: Exception) -> dict[str, Any]:
    details: dict[str, Any] = {}

    cause = exc.__cause__ or exc

    if isinstance(cause, RelaceAPIError):
        details = {
            "status_code": cause.status_code,
            "error_code": cause.code,
            "retryable": cause.retryable,
        }
        if cause.status_code in {401, 403}:
            details["recommended_action"] = "Check RELACE_API_KEY and retry."
        elif cause.status_code == 404:
            details["recommended_action"] = (
                "Cloud repo not found. Run cloud_sync() to recreate/upload."
            )
        elif cause.status_code == 429:
            details["recommended_action"] = "Rate limited. Retry later."
        return details

    if isinstance(cause, httpx.TimeoutException):
        return {
            "error_code": "timeout",
            "retryable": True,
            "recommended_action": "Check network connectivity and retry.",
        }

    if isinstance(cause, httpx.RequestError):
        return {
            "error_code": "network_error",
            "retryable": True,
            "recommended_action": "Check network connectivity, DNS/proxy, and RELACE_API_ENDPOINT.",
        }

    return details
