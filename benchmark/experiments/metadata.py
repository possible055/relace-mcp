import hashlib
import platform
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from relace_mcp.config import create_provider_config
from relace_mcp.config import settings as _settings

from .models import ExperimentManifest, ExperimentStateModel

if TYPE_CHECKING:
    from benchmark.schemas import DatasetCase
    from relace_mcp.config import RelaceConfig


def sanitize_endpoint_url(url: str) -> str:
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
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provider_snapshot(config: "RelaceConfig") -> dict[str, Any]:
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

    return {
        "provider": provider,
        "model": model,
        "base_url": sanitize_endpoint_url(base_url) if base_url else None,
        "timeout_seconds": _settings.SEARCH_TIMEOUT_SECONDS,
        "max_turns": _settings.SEARCH_MAX_TURNS,
        "temperature": _settings.SEARCH_TEMPERATURE,
        "prompt_file": _settings.SEARCH_PROMPT_FILE,
        "retrieval_backend": _settings.RETRIEVAL_BACKEND,
    }


def _environment_snapshot(config: "RelaceConfig") -> dict[str, Any]:
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

    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "relace_mcp_version": relace_mcp_version,
        "relace_mcp_commit": relace_mcp_commit,
        "base_dir": config.base_dir,
        "default_encoding": config.default_encoding,
    }


def build_experiment_manifest(
    *,
    config: "RelaceConfig",
    experiment_id: str,
    kind: str,
    experiment_root: Path,
    cases: list["DatasetCase"],
    run_config: dict[str, Any] | None,
    created_at: datetime,
    artifacts: dict[str, Any] | None = None,
) -> ExperimentManifest:
    run_meta = dict(run_config) if isinstance(run_config, dict) else {}
    parent_experiment_root = run_meta.get("parent_experiment_root")
    dataset_path_raw = run_meta.get("dataset_path")
    dataset_name = str(run_meta.get("dataset") or Path(str(dataset_path_raw or "unknown")).stem)

    dataset: dict[str, Any] = {
        "name": dataset_name,
        "case_count": len(cases),
        "repos_dir": str(run_meta.get("repos_dir") or ""),
        "sampling": {
            "limit": run_meta.get("limit"),
            "shuffle": bool(run_meta.get("shuffle", False)),
            "seed": run_meta.get("seed"),
        },
    }
    if isinstance(dataset_path_raw, str) and dataset_path_raw:
        dataset_path = Path(dataset_path_raw).expanduser()
        dataset["path"] = str(dataset_path)
        if dataset_path.is_file():
            dataset["sha256"] = _sha256_file(dataset_path)

    manifest = ExperimentManifest(
        experiment_id=experiment_id,
        kind=kind if kind in {"run", "grid", "trial"} else "run",
        name=experiment_root.name,
        experiment_root=experiment_root,
        created_at=created_at,
        dataset=dataset,
        search=_provider_snapshot(config),
        environment=_environment_snapshot(config),
        artifacts=dict(artifacts) if isinstance(artifacts, dict) else {},
        parent_experiment_id=Path(parent_experiment_root).name
        if isinstance(parent_experiment_root, str) and parent_experiment_root
        else None,
        tags=list(run_meta.get("tags", [])),
        config_snapshot=run_meta,
    )
    return manifest


def build_initial_state(total_cases: int) -> ExperimentStateModel:
    return ExperimentStateModel(
        status="pending",
        total_cases=total_cases,
        completed_cases=0,
        failed_cases=0,
        updated_at=datetime.now(UTC),
    )
