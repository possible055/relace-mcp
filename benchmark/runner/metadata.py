import hashlib
import platform
import subprocess  # nosec B404
import sys
from datetime import datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from relace_mcp.config import create_provider_config
from relace_mcp.config import settings as _settings

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
    artifact_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build reproducibility metadata for this benchmark run (no secrets)."""
    config_meta: dict[str, Any] = {
        "base_dir": config.base_dir,
        "default_encoding": config.default_encoding,
    }

    try:
        provider_config = create_provider_config(
            label="SEARCH",
            raw_provider=_settings.SEARCH_PROVIDER,
            raw_api_key=_settings.SEARCH_API_KEY,
            raw_endpoint=_settings.SEARCH_ENDPOINT,
            raw_model=_settings.SEARCH_MODEL,
            default_endpoint=_settings.SEARCH_DEFAULT_ENDPOINT,
            default_model=_settings.SEARCH_DEFAULT_MODEL,
            timeout=_settings.SEARCH_TIMEOUT_SECONDS,
            relace_api_key=config.api_key,
        )
        provider = provider_config.provider
        model = provider_config.model
        base_url = provider_config.base_url
    except RuntimeError:
        provider = (_settings.SEARCH_PROVIDER or _settings.RELACE_PROVIDER).lower()
        model = _settings.SEARCH_MODEL or (
            _settings.SEARCH_DEFAULT_MODEL if provider == _settings.RELACE_PROVIDER else ""
        )
        base_url = _settings.SEARCH_ENDPOINT or (
            _settings.SEARCH_DEFAULT_ENDPOINT if provider == _settings.RELACE_PROVIDER else ""
        )
    prompt_file = _settings.SEARCH_PROMPT_FILE

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
    experiment_type = str(run_meta.pop("experiment_type", "run") or "run")
    parent_experiment_root = run_meta.pop("parent_experiment_root", None)
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

    artifacts_meta = dict(artifact_metadata) if isinstance(artifact_metadata, dict) else {}
    experiment_root = artifacts_meta.get("experiment_root")
    experiment_name = None
    if isinstance(experiment_root, str) and experiment_root:
        experiment_name = Path(experiment_root).name

    return {
        "run": {
            **run_meta,
            "started_at_utc": started_at.isoformat(),
            "completed_at_utc": completed_at.isoformat(),
            "duration_s": round(duration_s, 1),
        },
        "experiment": {
            "type": experiment_type,
            "name": experiment_name,
            "root": experiment_root,
            "parent_root": parent_experiment_root
            if isinstance(parent_experiment_root, str)
            else None,
        },
        "config": config_meta,
        "dataset": dataset_info,
        "search": {
            "provider": provider,
            "model": model,
            "base_url": sanitize_endpoint_url(base_url) if base_url else None,
            "timeout_seconds": _settings.SEARCH_TIMEOUT_SECONDS,
            "max_turns": _settings.SEARCH_MAX_TURNS,
            "temperature": _settings.SEARCH_TEMPERATURE,
            "prompt_file": prompt_file,
        },
        "retrieval": {
            "backend": _settings.RETRIEVAL_BACKEND,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "relace_mcp_version": relace_mcp_version,
            "relace_mcp_git_commit": relace_mcp_commit,
        },
        "artifacts": artifacts_meta,
    }
