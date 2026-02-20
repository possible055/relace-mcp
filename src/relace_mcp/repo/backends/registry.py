import asyncio
import logging

logger = logging.getLogger(__name__)

_disabled_backends: set[str] = set()

_bg_index_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
_bg_index_rerun: dict[tuple[str, str], bool] = {}
_bg_codanna_pending: dict[tuple[str, str], set[str]] = {}


def is_backend_disabled(name: str) -> bool:
    return name in _disabled_backends


def disable_backend(name: str, reason: str) -> None:
    _disabled_backends.add(name)
    logger.warning("Backend %r disabled for this session: %s", name, reason)


def is_bg_index_running(base_dir: str, backend: str) -> bool:
    t = _bg_index_tasks.get((base_dir, backend))
    return t is not None and not t.done()
