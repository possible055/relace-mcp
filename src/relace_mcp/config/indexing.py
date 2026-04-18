from dataclasses import dataclass
from typing import Literal

from . import settings as _settings

LOCAL_INDEX_BACKENDS = frozenset({"codanna", "chunkhound"})
RetrievalBackend = Literal["relace", "codanna", "chunkhound", "none"]


@dataclass(frozen=True, slots=True)
class IndexRuntime:
    active_backend: RetrievalBackend
    cloud_tools_enabled: bool
    index_status_enabled: bool
    local_backend_enabled: bool
    background_monitor_allowed: bool


def validate_index_settings(*, api_key: str | None) -> None:
    backend = _settings.RETRIEVAL_BACKEND

    if backend == "relace" and not api_key:
        raise RuntimeError(
            "RELACE_API_KEY is required when MCP_RETRIEVAL_BACKEND=relace. "
            "Set RELACE_API_KEY or choose MCP_RETRIEVAL_BACKEND=codanna, chunkhound, or none."
        )


def resolve_index_runtime(
    *,
    base_dir: str | None,
) -> IndexRuntime:
    active_backend = _settings.RETRIEVAL_BACKEND
    local_backend_enabled = active_backend in LOCAL_INDEX_BACKENDS
    cloud_tools_enabled = active_backend == "relace"
    index_status_enabled = active_backend != "none"
    background_monitor_allowed = (
        local_backend_enabled
        and _settings.MCP_BACKGROUND_INDEX_MONITOR
        and _settings.AGENTIC_RETRIEVAL_ENABLED
        and bool(base_dir)
    )
    return IndexRuntime(
        active_backend=active_backend,
        cloud_tools_enabled=cloud_tools_enabled,
        index_status_enabled=index_status_enabled,
        local_backend_enabled=local_backend_enabled,
        background_monitor_allowed=background_monitor_allowed,
    )
