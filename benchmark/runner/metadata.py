import hashlib
import os
import platform
import subprocess  # nosec B404
import sys
from datetime import datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.config import settings as relace_settings
from relace_mcp.config.settings import RELACE_PROVIDER
from relace_mcp.tools.search.schemas.tool_schemas import get_tool_schemas

if TYPE_CHECKING:
    from benchmark.schemas import DatasetCase


def sanitize_endpoint_url(url: str) -> str:
    """Sanitize endpoint URL for logs/metadata (strip credentials, query, fragments)."""
    try:
        parts = urlsplit(url)
    except Exception:
        return url

    if not parts.scheme or not parts.netloc:
        return url

    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if not host:
        host = parts.netloc.split("@")[-1]

    netloc = host
    if parts.port is not None:
        netloc = f"{host}:{parts.port}"

    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_run_metadata(
    *,
    config: RelaceConfig,
    repos_dir: Path,
    cases: list["DatasetCase"],
    run_config: dict[str, Any] | None,
    started_at: datetime,
    completed_at: datetime,
    duration_ms: float,
) -> dict[str, Any]:
    """Build reproducibility metadata for this benchmark run (no secrets)."""
    # NOTE: Intentionally avoid recording any API keys.
    config_meta: dict[str, Any] = {
        "base_dir": config.base_dir,
        "default_encoding": config.default_encoding,
    }

    search_client = SearchLLMClient(config)
    provider_config = search_client._provider_config

    tool_schemas = get_tool_schemas(frozenset())
    tool_names: list[str] = []
    tool_has_strict = False
    for schema in tool_schemas:
        func = schema.get("function")
        if not isinstance(func, dict):
            continue
        name = func.get("name")
        if isinstance(name, str) and name:
            tool_names.append(name)
        if "strict" in func:
            tool_has_strict = True
    tool_names = sorted(set(tool_names))

    request_params: dict[str, Any] = {
        "temperature": relace_settings.SEARCH_TEMPERATURE,
        "merger_temperature": relace_settings.MERGER_TEMPERATURE,
        "top_p": 0.95,
        "top_k": 100 if provider_config.api_compat == RELACE_PROVIDER else None,
        "repetition_penalty": (1.0 if provider_config.api_compat == RELACE_PROVIDER else None),
    }
    search_prompt_file = os.getenv("SEARCH_PROMPT_FILE", "").strip() or None

    case_list = [
        {
            "id": c.id,
            "repo": c.repo,
            "base_commit": c.base_commit,
            "issue_url": c.issue_url,
            "pr_url": c.pr_url,
        }
        for c in cases
    ]

    relace_mcp_commit: str | None = None
    try:
        project_root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(  # nosec B603 B607
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        relace_mcp_commit = completed.stdout.strip() or None
    except Exception:
        relace_mcp_commit = None

    relace_mcp_version: str | None = None
    try:
        relace_mcp_version = importlib_metadata.version("relace-mcp")
    except importlib_metadata.PackageNotFoundError:
        relace_mcp_version = None

    run_meta = dict(run_config) if isinstance(run_config, dict) else {}
    run_meta.setdefault("cases_loaded", len(cases))

    dataset_info: dict[str, Any] = {
        "repos_dir": str(repos_dir),
        "cases": case_list,
    }
    dataset_path = run_meta.get("dataset_path")
    if isinstance(dataset_path, str) and dataset_path:
        try:
            dataset_file = Path(dataset_path).expanduser()
            if dataset_file.is_file():
                dataset_info["dataset_path"] = str(dataset_file)
                dataset_info["dataset_bytes"] = dataset_file.stat().st_size
                dataset_info["dataset_sha256"] = _sha256_file(dataset_file)
        except Exception:
            pass

    parallel_tool_calls_requested = bool(relace_settings.SEARCH_PARALLEL_TOOL_CALLS)
    parallel_tool_calls_effective = parallel_tool_calls_requested
    if (
        provider_config.api_compat != RELACE_PROVIDER
        and parallel_tool_calls_effective
        and tool_has_strict
    ):
        parallel_tool_calls_effective = False

    return {
        "run": {
            **run_meta,
            "started_at_utc": started_at.isoformat(),
            "completed_at_utc": completed_at.isoformat(),
            "duration_ms": round(duration_ms, 2),
        },
        "config": config_meta,
        "dataset": dataset_info,
        "search": {
            "provider": provider_config.provider,
            "api_compat": provider_config.api_compat,
            "base_url": sanitize_endpoint_url(provider_config.base_url),
            "model": provider_config.model,
            "timeout_seconds": relace_settings.SEARCH_TIMEOUT_SECONDS,
            "max_turns": relace_settings.SEARCH_MAX_TURNS,
            "dual_channel_turns": relace_settings.SEARCH_DUAL_CHANNEL_TURNS,
            "prompt_file": search_prompt_file,
            "tools": tool_names,
            "tool_strict": tool_has_strict,
            "parallel_tool_calls_requested": parallel_tool_calls_requested,
            "parallel_tool_calls_effective": parallel_tool_calls_effective,
            **request_params,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "relace_mcp_version": relace_mcp_version,
            "relace_mcp_git_commit": relace_mcp_commit,
        },
    }
