from relace_mcp.observability import log_event, log_trace_event


def log_lsp_server_start(
    language_id: str,
    workspace: str,
    command: list[str],
    latency_ms: float,
) -> None:
    log_event(
        {
            "kind": "lsp_server_start",
            "level": "info",
            "language_id": language_id,
            "workspace": workspace,
            "command_preview": command[0] if command else "",
            "latency_ms": int(latency_ms),
        }
    )
    log_trace_event(
        {
            "kind": "lsp_server_start",
            "language_id": language_id,
            "workspace": workspace,
            "command": command,
            "latency_ms": int(latency_ms),
        }
    )


def log_lsp_server_stop(
    language_id: str,
    workspace: str,
) -> None:
    log_event(
        {
            "kind": "lsp_server_stop",
            "level": "info",
            "language_id": language_id,
            "workspace": workspace,
        }
    )


def log_lsp_server_error(
    language_id: str,
    workspace: str,
    error: str,
    error_type: str,
) -> None:
    log_event(
        {
            "kind": "lsp_server_error",
            "level": "error",
            "language_id": language_id,
            "workspace": workspace,
            "error": error,
            "error_type": error_type,
        }
    )
    log_trace_event(
        {
            "kind": "lsp_server_error",
            "language_id": language_id,
            "workspace": workspace,
            "error": error,
            "error_type": error_type,
        }
    )


def log_lsp_request_error(
    method: str,
    error: str,
    error_type: str,
) -> None:
    log_event(
        {
            "kind": "lsp_request_error",
            "level": "warning",
            "method": method,
            "error": error,
            "error_type": error_type,
        }
    )


def log_lsp_client_created(
    language_id: str,
    workspace: str,
    pool_size: int,
) -> None:
    log_event(
        {
            "kind": "lsp_client_created",
            "level": "info",
            "language_id": language_id,
            "workspace": workspace,
            "pool_size": pool_size,
        }
    )


def log_lsp_client_evicted(
    language_id: str,
    workspace: str,
    pool_size: int,
    reason: str,
) -> None:
    log_event(
        {
            "kind": "lsp_client_evicted",
            "level": "info",
            "language_id": language_id,
            "workspace": workspace,
            "pool_size": pool_size,
            "reason": reason,
        }
    )
