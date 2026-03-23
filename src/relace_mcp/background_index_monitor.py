import asyncio
import logging
import secrets
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any

from .config import settings as _settings
from .observability import log_event
from .repo.backends.chunkhound import schedule_bg_chunkhound_index
from .repo.backends.codanna import schedule_bg_codanna_full_index
from .repo.backends.locking import BackendIndexRunResult, supports_backend_index_locking
from .repo.backends.registry import (
    get_bg_index_task,
    is_backend_disabled,
    is_bg_index_running,
)
from .repo.freshness import classify_local_index_freshness

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from .config import RelaceConfig

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 60.0
_BACKOFF_MAX_SECONDS = 900.0


class BackgroundIndexMonitor:
    def __init__(self, config: "RelaceConfig") -> None:
        self._config = config
        self._requested = _settings.MCP_BACKGROUND_INDEX_MONITOR
        # Settings are captured at construction time. The monitor does not re-read them
        # after start(); restart the server to apply changes to interval/delay.
        self._interval_seconds = float(_settings.MCP_BACKGROUND_INDEX_INTERVAL_SECONDS)
        self._initial_delay_seconds = float(_settings.MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS)
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._active_backend: str | None = None
        self._reason = "disabled_by_config"
        self._last_status: str | None = None
        self._last_error: str | None = None
        self._failure_count = 0
        self._warned_keys: set[str] = set()

    @property
    def requested(self) -> bool:
        return self._requested

    def _is_task_running(self) -> bool:
        task = self._task
        return task is not None and not task.done()

    def summary(self) -> dict[str, Any]:
        enabled = self._is_task_running()
        return {
            "enabled": enabled,
            "requested": self._requested,
            "reason": None if enabled else self._reason,
            "active_backend": self._active_backend,
            "interval_seconds": self._interval_seconds if self._requested else None,
            "initial_delay_seconds": self._initial_delay_seconds if self._requested else None,
            "base_dir": self._config.base_dir,
            "last_status": self._last_status,
            "last_error": self._last_error,
        }

    @asynccontextmanager
    async def lifespan(self, _server: "FastMCP") -> AsyncIterator[dict[str, Any]]:
        await self.start()
        try:
            yield {}
        finally:
            await self.stop()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return

        self._active_backend, self._reason = self._resolve_startup_state()
        if self._active_backend is None:
            self._maybe_log_startup_reason()
            return

        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"relace-bg-index-monitor:{self._active_backend}",
        )
        self._running = True
        log_event(
            {
                "kind": "background_index_monitor_started",
                "level": "info",
                "backend": self._active_backend,
                "base_dir": self._config.base_dir,
                "interval_seconds": self._interval_seconds,
                "initial_delay_seconds": self._initial_delay_seconds,
            }
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        self._running = False
        if task is None:
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def _resolve_startup_state(self) -> tuple[str | None, str]:
        if not self._requested:
            return None, "disabled_by_config"
        if not _settings.AGENTIC_RETRIEVAL_ENABLED:
            return None, "agentic_retrieval_disabled"
        if not self._config.base_dir:
            return None, "base_dir_not_pinned"
        if not supports_backend_index_locking():
            return None, "locking_unavailable"

        backend = _settings.RETRIEVAL_BACKEND
        if backend in ("relace", "none"):
            return None, "backend_not_local"

        if backend == "auto":
            for candidate in ("codanna", "chunkhound"):
                if is_backend_disabled(candidate):
                    continue
                if shutil.which(candidate):
                    return candidate, "ok"
            return None, "no_local_backend_available"

        if is_backend_disabled(backend):
            return None, "backend_disabled"
        if not shutil.which(backend):
            return None, "cli_not_found"
        return backend, "ok"

    def _maybe_log_startup_reason(self) -> None:
        if not self._requested:
            return

        messages = {
            "agentic_retrieval_disabled": (
                logging.INFO,
                "Background index monitor requested but MCP_SEARCH_RETRIEVAL is disabled.",
            ),
            "base_dir_not_pinned": (
                logging.WARNING,
                "Background index monitor requested but MCP_BASE_DIR is not set. "
                "Pin the repo with MCP_BASE_DIR to enable periodic refresh.",
            ),
            "locking_unavailable": (
                logging.WARNING,
                "Background index monitor requested but host-local file locking is unavailable "
                "on this platform. Monitor will stay disabled.",
            ),
            "backend_not_local": (
                logging.INFO,
                "Background index monitor requested but the configured retrieval backend is not local.",
            ),
            "no_local_backend_available": (
                logging.WARNING,
                "Background index monitor requested but no local retrieval backend CLI is installed.",
            ),
            "backend_disabled": (
                logging.WARNING,
                "Background index monitor requested but the selected backend is disabled in this process.",
            ),
            "cli_not_found": (
                logging.WARNING,
                "Background index monitor requested but the selected local backend CLI is not installed.",
            ),
        }
        level, message = messages.get(
            self._reason,
            (logging.INFO, f"Background index monitor disabled: {self._reason}"),
        )
        self._log_once(f"startup:{self._reason}", level, message)

    async def _run_loop(self) -> None:
        delay = self._initial_delay_seconds
        while True:
            await asyncio.sleep(delay)
            try:
                result = await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._failure_count += 1
                self._last_status = "error"
                self._last_error = str(exc)
                logger.warning(
                    "Background index monitor unexpected error: %s",
                    exc,
                    exc_info=True,
                )
                delay = min(
                    _BACKOFF_BASE_SECONDS * (2 ** (self._failure_count - 1)),
                    _BACKOFF_MAX_SECONDS,
                )
                continue
            self._last_status = result.status
            self._last_error = result.reason

            if result.status in {
                "lock_held",
                "lock_error",
                "cli_not_found",
                "backend_disabled",
                "spawn_error",
                "timeout",
                "nonzero_exit",
                "error",
            }:
                self._failure_count += 1
                delay = min(
                    _BACKOFF_BASE_SECONDS * (2 ** (self._failure_count - 1)),
                    _BACKOFF_MAX_SECONDS,
                )
            else:
                self._failure_count = 0
                delay = self._with_jitter(self._interval_seconds)

    async def _tick(self) -> BackendIndexRunResult:
        base_dir = self._config.base_dir
        backend = self._active_backend
        if not base_dir or not backend:
            return BackendIndexRunResult(status="disabled", reason=self._reason)

        if is_backend_disabled(backend):
            self._log_once(
                f"disabled:{backend}",
                logging.WARNING,
                f"Background index monitor skipped because {backend} is disabled in this process.",
            )
            return BackendIndexRunResult(status="backend_disabled")

        if not shutil.which(backend):
            self._log_once(
                f"cli_missing:{backend}",
                logging.WARNING,
                f"Background index monitor skipped because {backend} CLI is not installed.",
            )
            return BackendIndexRunResult(status="cli_not_found")

        if is_bg_index_running(base_dir, backend):
            return BackendIndexRunResult(status="bg_index_running")

        freshness = classify_local_index_freshness(base_dir, backend)
        if not freshness.refresh_recommended:
            return BackendIndexRunResult(
                status=freshness.freshness,
                reason=freshness.reason,
            )

        log_event(
            {
                "kind": "background_index_monitor_tick",
                "level": "info",
                "backend": backend,
                "base_dir": base_dir,
                "freshness": freshness.freshness,
                "reason": freshness.reason,
            }
        )

        if backend == "codanna":
            schedule_bg_codanna_full_index(base_dir)
        else:
            schedule_bg_chunkhound_index(base_dir)

        task = get_bg_index_task(base_dir, backend)
        if task is None:
            logger.warning(
                "Background index monitor scheduled %s index but no task was registered.",
                backend,
            )
            return BackendIndexRunResult(
                status="error",
                reason="bg_task_not_registered",
            )
        return await asyncio.shield(task)

    def _with_jitter(self, seconds: float) -> float:
        basis_points = secrets.randbelow(3001) - 1500
        return max(1.0, seconds * (1.0 + basis_points / 10000.0))

    def _log_once(self, key: str, level: int, message: str) -> None:
        if key in self._warned_keys:
            return
        self._warned_keys.add(key)
        logger.log(level, message)


def get_background_index_monitor_summary(mcp: Any) -> dict[str, Any]:
    monitor = getattr(mcp, "_relace_background_index_monitor", None)
    if isinstance(monitor, BackgroundIndexMonitor):
        return monitor.summary()
    return {
        "enabled": False,
        "requested": False,
        "reason": "uninitialized",
        "active_backend": None,
        "interval_seconds": None,
        "initial_delay_seconds": None,
        "base_dir": None,
        "last_status": None,
        "last_error": None,
    }
