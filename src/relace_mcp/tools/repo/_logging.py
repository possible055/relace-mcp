from typing import Any

from ...observability import log_event

__all__ = ["log_cloud_event", "_extract_error_fields"]


def log_cloud_event(kind: str, trace_id: str, **kw: Any) -> None:
    log_event({"kind": kind, "trace_id": trace_id, **kw})


def _extract_error_fields(result: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {"error": result.get("error") or result.get("message")}
    for key in ("status_code", "error_code", "retryable", "recommended_action"):
        if key in result:
            fields[key] = result[key]
    return fields
