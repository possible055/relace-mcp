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

from relace_mcp.config import settings as relace_settings

if TYPE_CHECKING:
    from benchmark.schemas import DatasetCase
    from relace_mcp.config import RelaceConfig


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
    config: "RelaceConfig",
    repos_dir: Path,
    cases: list["DatasetCase"],
    run_config: dict[str, Any] | None,
    started_at: datetime,
    completed_at: datetime,
    duration_s: float,
) -> dict[str, Any]:
    """Build reproducibility metadata for this benchmark run (no secrets)."""
    config_meta: dict[str, Any] = {
        "base_dir": config.base_dir,
        "default_encoding": config.default_encoding,
    }

    # Get provider info from environment/settings (avoid private attribute access)
    provider = os.getenv("SEARCH_PROVIDER", "relace").strip().lower()
    model = os.getenv("SEARCH_MODEL", "").strip()
    base_url = os.getenv("SEARCH_ENDPOINT", "").strip()
    prompt_file = os.getenv("SEARCH_PROMPT_FILE", "").strip() or None

    case_list = [
        {
            "id": c.id,
            "repo": c.repo,
            "base_commit": c.base_commit,
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
                dataset_info["dataset_sha256"] = _sha256_file(dataset_file)
        except Exception:
            pass

    return {
        "run": {
            **run_meta,
            "started_at_utc": started_at.isoformat(),
            "completed_at_utc": completed_at.isoformat(),
            "duration_s": round(duration_s, 1),
        },
        "config": config_meta,
        "dataset": dataset_info,
        "search": {
            "provider": provider,
            "model": model,
            "base_url": sanitize_endpoint_url(base_url) if base_url else None,
            "timeout_seconds": relace_settings.SEARCH_TIMEOUT_SECONDS,
            "max_turns": relace_settings.SEARCH_MAX_TURNS,
            "temperature": relace_settings.SEARCH_TEMPERATURE,
            "prompt_file": prompt_file,
        },
        "retrieval": {
            "backend": os.getenv("MCP_RETRIEVAL_BACKEND", "auto"),
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "relace_mcp_version": relace_mcp_version,
            "relace_mcp_git_commit": relace_mcp_commit,
        },
    }
