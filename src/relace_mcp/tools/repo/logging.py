from typing import Any

from ..apply.logging import log_event


def log_cloud_sync_start(
    trace_id: str,
    requested_base_dir: str,
    base_dir: str,
    repo_name: str,
    cloud_repo_name: str,
    force: bool,
    mirror: bool,
) -> None:
    log_event(
        {
            "kind": "cloud_sync_start",
            "trace_id": trace_id,
            "requested_base_dir": requested_base_dir,
            "base_dir": base_dir,
            "repo_name": repo_name,
            "cloud_repo_name": cloud_repo_name,
            "force": force,
            "mirror": mirror,
        }
    )


def log_cloud_sync_complete(trace_id: str, result: dict[str, Any]) -> None:
    log_event(
        {
            "kind": "cloud_sync_complete",
            "trace_id": trace_id,
            "repo_id": result.get("repo_id"),
            "repo_name": result.get("repo_name"),
            "cloud_repo_name": result.get("cloud_repo_name"),
            "repo_head": result.get("repo_head"),
            "sync_mode": result.get("sync_mode"),
            "is_incremental": result.get("is_incremental"),
            "files_created": result.get("files_created"),
            "files_updated": result.get("files_updated"),
            "files_deleted": result.get("files_deleted"),
            "files_unchanged": result.get("files_unchanged"),
            "files_skipped": result.get("files_skipped"),
            "files_found": result.get("files_found"),
            "files_selected": result.get("files_selected"),
            "files_truncated": result.get("files_truncated"),
            "warnings_count": len(result.get("warnings") or []),
        }
    )


def log_cloud_sync_error(
    trace_id: str, repo_name: str | None, cloud_repo_name: str | None, result: dict[str, Any]
) -> None:
    event = {
        "kind": "cloud_sync_error",
        "trace_id": trace_id,
        "repo_name": repo_name,
        "cloud_repo_name": cloud_repo_name,
        "error": result.get("error") or result.get("message"),
    }
    for key in ("status_code", "error_code", "retryable", "recommended_action"):
        if key in result:
            event[key] = result[key]
    log_event(event)


def log_cloud_search_start(
    trace_id: str,
    repo_name: str,
    cloud_repo_name: str,
    query: str,
    branch: str,
    score_threshold: float,
    token_limit: int,
) -> None:
    q = query or ""
    log_event(
        {
            "kind": "cloud_search_start",
            "trace_id": trace_id,
            "repo_name": repo_name,
            "cloud_repo_name": cloud_repo_name,
            "query_preview": q[:500] if len(q) > 500 else q,
            "branch": branch,
            "score_threshold": score_threshold,
            "token_limit": token_limit,
        }
    )


def log_cloud_search_complete(trace_id: str, result: dict[str, Any]) -> None:
    log_event(
        {
            "kind": "cloud_search_complete",
            "trace_id": trace_id,
            "repo_id": result.get("repo_id"),
            "repo_name": result.get("repo_name"),
            "cloud_repo_name": result.get("cloud_repo_name"),
            "branch": result.get("branch"),
            "hash": result.get("hash"),
            "result_count": result.get("result_count"),
            "warnings_count": len(result.get("warnings") or []),
        }
    )


def log_cloud_search_error(
    trace_id: str, repo_name: str | None, cloud_repo_name: str | None, result: dict[str, Any]
) -> None:
    event = {
        "kind": "cloud_search_error",
        "trace_id": trace_id,
        "repo_name": repo_name,
        "cloud_repo_name": cloud_repo_name,
        "error": result.get("error") or result.get("message"),
    }
    for key in ("status_code", "error_code", "retryable", "recommended_action"):
        if key in result:
            event[key] = result[key]
    log_event(event)


def log_cloud_info_start(trace_id: str, repo_name: str, cloud_repo_name: str) -> None:
    log_event(
        {
            "kind": "cloud_info_start",
            "trace_id": trace_id,
            "repo_name": repo_name,
            "cloud_repo_name": cloud_repo_name,
        }
    )


def log_cloud_info_complete(trace_id: str, result: dict[str, Any]) -> None:
    log_event(
        {
            "kind": "cloud_info_complete",
            "trace_id": trace_id,
            "repo_name": result.get("repo_name"),
            "cloud_repo_name": result.get("cloud_repo_name"),
            "needs_sync": ((result.get("status") or {}).get("needs_sync")),
            "ref_changed": ((result.get("status") or {}).get("ref_changed")),
            "warnings_count": len(result.get("warnings") or []),
        }
    )


def log_cloud_info_error(
    trace_id: str, repo_name: str | None, cloud_repo_name: str | None, result: dict[str, Any]
) -> None:
    event = {
        "kind": "cloud_info_error",
        "trace_id": trace_id,
        "repo_name": repo_name,
        "cloud_repo_name": cloud_repo_name,
        "error": result.get("error") or result.get("message"),
    }
    for key in ("status_code", "error_code", "retryable", "recommended_action"):
        if key in result:
            event[key] = result[key]
    log_event(event)


def log_cloud_list_start(trace_id: str) -> None:
    log_event({"kind": "cloud_list_start", "trace_id": trace_id})


def log_cloud_list_complete(trace_id: str, result: dict[str, Any]) -> None:
    log_event(
        {
            "kind": "cloud_list_complete",
            "trace_id": trace_id,
            "count": result.get("count"),
            "has_more": result.get("has_more"),
        }
    )


def log_cloud_list_error(trace_id: str, result: dict[str, Any]) -> None:
    event = {
        "kind": "cloud_list_error",
        "trace_id": trace_id,
        "error": result.get("error") or result.get("message"),
    }
    for key in ("status_code", "error_code", "retryable", "recommended_action"):
        if key in result:
            event[key] = result[key]
    log_event(event)


def log_cloud_clear_start(
    trace_id: str, repo_name: str | None, cloud_repo_name: str | None, confirm: bool
) -> None:
    log_event(
        {
            "kind": "cloud_clear_start",
            "trace_id": trace_id,
            "repo_name": repo_name,
            "cloud_repo_name": cloud_repo_name,
            "confirm": confirm,
        }
    )


def log_cloud_clear_complete(trace_id: str, result: dict[str, Any]) -> None:
    log_event(
        {
            "kind": "cloud_clear_complete",
            "trace_id": trace_id,
            "status": result.get("status"),
            "repo_id": result.get("repo_id"),
            "repo_name": result.get("repo_name"),
            "cloud_repo_name": result.get("cloud_repo_name"),
        }
    )


def log_cloud_clear_error(
    trace_id: str, repo_name: str | None, cloud_repo_name: str | None, result: dict[str, Any]
) -> None:
    event = {
        "kind": "cloud_clear_error",
        "trace_id": trace_id,
        "repo_name": repo_name,
        "cloud_repo_name": cloud_repo_name,
        "error": result.get("error") or result.get("message"),
    }
    for key in ("status_code", "error_code", "retryable", "recommended_action"):
        if key in result:
            event[key] = result[key]
    log_event(event)
