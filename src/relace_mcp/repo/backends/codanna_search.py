import logging
from typing import Any

from .cli import _run_cli_json
from .codanna_indexing import _build_codanna_env, _ensure_codanna_index
from .errors import ExternalCLIError

logger = logging.getLogger(__name__)


def _is_codanna_index_missing_error(message: str) -> bool:
    lowered = message.lower()
    return "index" in lowered and (
        "missing" in lowered or "not found" in lowered or "not built" in lowered
    )


def _extract_codanna_results(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []

    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")
        context = item.get("context")
        filename = None
        if isinstance(symbol, dict):
            filename = symbol.get("file_path")
        if not filename and isinstance(context, dict):
            filename = context.get("file_path")
        if not filename:
            continue

        raw_score = item.get("score")
        try:
            score = float(raw_score) if raw_score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0

        results.append({"filename": filename, "score": score})

    return results


def _codanna_health_probe(base_dir: str) -> None:
    try:
        _run_cli_json(
            [
                "codanna",
                "mcp",
                "semantic_search_with_context",
                "query:healthcheck",
                "limit:1",
                "threshold:0",
                "--json",
            ],
            base_dir,
            timeout=30,
        )
    except RuntimeError as exc:
        message = str(exc)
        if _is_codanna_index_missing_error(message):
            raise ExternalCLIError(
                backend="codanna",
                kind="index_missing",
                message="Codanna index not built. Run `codanna index` to build it.",
                command=["codanna", "mcp"],
            ) from exc
        raise ExternalCLIError(
            backend="codanna",
            kind="nonzero_exit",
            message=message,
            command=["codanna", "mcp"],
        ) from exc


def codanna_search(
    query: str,
    *,
    base_dir: str,
    limit: int = 8,
    threshold: float = 0.3,
    _retry: bool = False,
    allow_auto_index: bool = True,
) -> list[dict[str, Any]]:
    """Run Codanna semantic search and return filename/score pairs.

    This calls the external `codanna` CLI. If the index is missing and
    `allow_auto_index=True`, it attempts to create the index once and retries.
    """
    command = [
        "codanna",
        "mcp",
        "semantic_search_with_context",
        f"query:{query}",
        f"limit:{limit}",
        f"threshold:{threshold}",
        "--json",
    ]

    try:
        data = _run_cli_json(command, base_dir, timeout=60)
    except RuntimeError as exc:
        message = str(exc)
        lowered = message.lower()
        if "cli not found" in lowered:
            raise ExternalCLIError(
                backend="codanna",
                kind="cli_not_found",
                message="codanna CLI not found. Install with: pip install codanna",
                command=command,
            ) from exc
        if _is_codanna_index_missing_error(message):
            if not allow_auto_index or _retry:
                raise ExternalCLIError(
                    backend="codanna",
                    kind="index_missing",
                    message="Codanna index creation failed or index still not found",
                    command=command,
                ) from exc

            logger.debug("Codanna index not found, attempting to create...")
            try:
                _ensure_codanna_index(base_dir, _build_codanna_env())
            except RuntimeError as reindex_exc:
                raise ExternalCLIError(
                    backend="codanna",
                    kind="index_missing",
                    message=f"Codanna auto-index failed: {reindex_exc}",
                    command=["codanna", "index"],
                ) from reindex_exc

            return codanna_search(
                query,
                base_dir=base_dir,
                limit=limit,
                threshold=threshold,
                _retry=True,
                allow_auto_index=allow_auto_index,
            )

        raise ExternalCLIError(
            backend="codanna",
            kind="nonzero_exit",
            message=message,
            command=command,
        ) from exc

    return _extract_codanna_results(data)
