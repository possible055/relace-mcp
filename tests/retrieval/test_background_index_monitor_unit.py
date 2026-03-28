import asyncio
import logging
import os
from unittest.mock import AsyncMock, patch

import pytest

import relace_mcp.repo.backends.chunkhound as chunkhound_backend
import relace_mcp.repo.backends.codanna_indexing as codanna_indexing
import relace_mcp.repo.backends.locking as backend_locking
import relace_mcp.repo.monitor as bgmon
from relace_mcp.config import RelaceConfig
from relace_mcp.repo.backends.locking import (
    BackendIndexLease,
    BackendIndexRunResult,
    supports_backend_index_locking,
    try_acquire_backend_index_lock,
)
from relace_mcp.repo.backends.registry import (
    _bg_codanna_pending,
    _bg_index_rerun,
    _bg_index_tasks,
    is_bg_index_running,
)
from relace_mcp.repo.freshness import FreshnessStatus
from relace_mcp.repo.monitor import BackgroundIndexMonitor


def _configure_monitor_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    requested: bool = True,
    retrieval_enabled: bool = True,
    retrieval_backend: str = "codanna",
    interval_seconds: int = 300,
    initial_delay_seconds: int = 30,
) -> None:
    monkeypatch.setattr(bgmon._settings, "MCP_BACKGROUND_INDEX_MONITOR", requested)
    monkeypatch.setattr(bgmon._settings, "AGENTIC_RETRIEVAL_ENABLED", retrieval_enabled)
    monkeypatch.setattr(bgmon._settings, "RETRIEVAL_BACKEND", retrieval_backend)
    monkeypatch.setattr(bgmon._settings, "MCP_BACKGROUND_INDEX_INTERVAL_SECONDS", interval_seconds)
    monkeypatch.setattr(
        bgmon._settings,
        "MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS",
        initial_delay_seconds,
    )


class TestBackgroundIndexMonitor:
    @pytest.mark.asyncio
    async def test_start_requires_pinned_base_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure_monitor_settings(monkeypatch)

        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=None))
        await monitor.start()

        summary = monitor.summary()
        assert summary["enabled"] is False
        assert summary["reason"] == "base_dir_not_pinned"

    @pytest.mark.asyncio
    async def test_start_is_idempotent_for_single_server_instance(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_monitor_settings(monkeypatch, retrieval_backend="chunkhound")

        with patch("relace_mcp.repo.monitor.shutil.which", return_value="/usr/bin/fake"):
            monitor = BackgroundIndexMonitor(
                RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))
            )
            await monitor.start()
            first_task = monitor._task
            await monitor.start()
            second_task = monitor._task
            await monitor.stop()

        assert first_task is not None
        assert first_task is second_task

    @pytest.mark.asyncio
    async def test_auto_mode_prefers_codanna_and_runs_only_active_backend(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_monitor_settings(monkeypatch, retrieval_backend="auto")
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path)))

        with patch(
            "relace_mcp.repo.monitor.shutil.which",
            side_effect=lambda name: (
                f"/usr/bin/{name}" if name in {"codanna", "chunkhound"} else None
            ),
        ):
            backend, reason = monitor._resolve_startup_state()

        assert backend == "codanna"
        assert reason == "ok"

        monitor._active_backend = backend
        scheduled_task = asyncio.create_task(
            asyncio.sleep(0, result=BackendIndexRunResult(status="completed"))
        )
        with (
            patch.object(
                bgmon,
                "classify_local_index_freshness",
                return_value=FreshnessStatus(
                    freshness="stale",
                    hints_usable=True,
                    refresh_recommended=True,
                    reason="git_head_changed",
                ),
            ),
            patch("relace_mcp.repo.monitor.shutil.which", return_value="/usr/bin/fake"),
            patch.object(bgmon, "schedule_bg_codanna_full_index") as mock_codanna,
            patch.object(bgmon, "schedule_bg_chunkhound_index") as mock_chunkhound,
            patch.object(bgmon, "get_bg_index_task", return_value=scheduled_task),
        ):
            result = await monitor._tick()

        assert result.status == "completed"
        mock_codanna.assert_called_once_with(str(tmp_path))
        mock_chunkhound.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["lock_held", "lock_error"])
    async def test_run_loop_uses_backoff_after_lock_failures(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, status: str
    ) -> None:
        _configure_monitor_settings(
            monkeypatch,
            retrieval_backend="chunkhound",
            interval_seconds=300,
            initial_delay_seconds=1,
        )
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path)))

        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)
            if len(delays) >= 2:
                raise asyncio.CancelledError()

        monitor._tick = AsyncMock(  # type: ignore[method-assign]
            return_value=BackendIndexRunResult(status=status)
        )

        with (
            patch.object(monitor, "_with_jitter", side_effect=lambda seconds: seconds),
            patch("relace_mcp.repo.monitor.asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await monitor._run_loop()

        assert delays == [1, 60.0]

    @pytest.mark.asyncio
    async def test_run_loop_recovers_after_unexpected_tick_exception(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _configure_monitor_settings(
            monkeypatch,
            retrieval_backend="chunkhound",
            interval_seconds=300,
            initial_delay_seconds=1,
        )
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path)))

        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)
            if len(delays) >= 3:
                raise asyncio.CancelledError()

        monitor._tick = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                OSError("disk read failed"),
                BackendIndexRunResult(status="fresh", reason="up_to_date"),
            ]
        )

        caplog.set_level(logging.WARNING)
        with (
            patch.object(monitor, "_with_jitter", side_effect=lambda seconds: seconds),
            patch("relace_mcp.repo.monitor.asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await monitor._run_loop()

        assert delays == [1, 60.0, 300]
        assert monitor._tick.await_count == 2  # type: ignore[attr-defined]
        assert monitor._last_status == "fresh"
        assert monitor._last_error == "up_to_date"
        assert any(
            "Background index monitor unexpected error" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_summary_uses_task_liveness_not_running_flag(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_monitor_settings(monkeypatch)
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path)))
        monitor._running = True
        monitor._reason = "ok"

        finished_task = asyncio.create_task(asyncio.sleep(0))
        await finished_task
        monitor._task = finished_task

        summary = monitor.summary()
        assert summary["enabled"] is False

    @pytest.mark.asyncio
    async def test_tick_registers_monitor_triggered_run_in_bg_registry(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_monitor_settings(monkeypatch, retrieval_backend="codanna")
        base_dir = str(tmp_path)
        key = (base_dir, "codanna")
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=base_dir))
        monitor._active_backend = "codanna"

        _bg_index_tasks.pop(key, None)
        _bg_index_rerun.pop(key, None)
        _bg_codanna_pending.pop(key, None)

        started = asyncio.Event()
        release = asyncio.Event()
        call_count = 0

        async def fake_full_index(_base_dir: str) -> BackendIndexRunResult:
            nonlocal call_count
            call_count += 1
            started.set()
            await release.wait()
            return BackendIndexRunResult(status="completed")

        try:
            with (
                patch.object(
                    bgmon,
                    "classify_local_index_freshness",
                    return_value=FreshnessStatus(
                        freshness="stale",
                        hints_usable=True,
                        refresh_recommended=True,
                        reason="git_head_changed",
                    ),
                ),
                patch(
                    "relace_mcp.repo.monitor.shutil.which",
                    return_value="/usr/bin/fake",
                ),
                patch(
                    "relace_mcp.repo.backends.codanna_indexing._async_run_codanna_full_index",
                    side_effect=fake_full_index,
                ),
            ):
                tick_task = asyncio.create_task(monitor._tick())
                await asyncio.wait_for(started.wait(), timeout=2)

                assert is_bg_index_running(base_dir, "codanna") is True
                running_task = _bg_index_tasks[key]

                codanna_indexing.schedule_bg_codanna_full_index(base_dir)
                await asyncio.sleep(0)

                assert _bg_index_tasks[key] is running_task
                assert call_count == 1

                release.set()
                result = await asyncio.wait_for(tick_task, timeout=2)
                assert result.status == "completed"

                await asyncio.sleep(0)
                rerun_task = _bg_index_tasks.get(key)
                if rerun_task is not None and rerun_task is not running_task:
                    await asyncio.wait_for(rerun_task, timeout=2)
        finally:
            _bg_index_tasks.pop(key, None)
            _bg_index_rerun.pop(key, None)
            _bg_codanna_pending.pop(key, None)

    @pytest.mark.asyncio
    async def test_cli_missing_logs_warning_once(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _configure_monitor_settings(monkeypatch, retrieval_backend="chunkhound")
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path)))
        monitor._active_backend = "chunkhound"

        caplog.set_level(logging.WARNING)
        with patch("relace_mcp.repo.monitor.shutil.which", return_value=None):
            first = await monitor._tick()
            second = await monitor._tick()

        assert first.status == "cli_not_found"
        assert second.status == "cli_not_found"
        messages = [
            record.message for record in caplog.records if "CLI is not installed" in record.message
        ]
        assert len(messages) == 1


class TestBackendIndexLock:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("target", ["chunkhound", "codanna_index", "codanna_full"])
    async def test_lock_error_status_is_normalized(self, tmp_path, target: str) -> None:
        base_dir = str(tmp_path)
        lease = BackendIndexLease(
            backend="codanna" if target.startswith("codanna") else "chunkhound",
            base_dir=base_dir,
            lock_path=f"{base_dir}/test.lock",
            acquired=False,
            reason="lock_error:[Errno 13] Permission denied",
        )

        if target == "chunkhound":
            with patch(
                "relace_mcp.repo.backends.chunkhound.try_acquire_backend_index_lock",
                return_value=lease,
            ):
                result = await chunkhound_backend._async_run_chunkhound_index(base_dir)
        elif target == "codanna_index":
            with patch(
                "relace_mcp.repo.backends.codanna_indexing.try_acquire_backend_index_lock",
                return_value=lease,
            ):
                result = await codanna_indexing._async_run_codanna_index(
                    f"{base_dir}/sample.py",
                    base_dir,
                )
        else:
            with patch(
                "relace_mcp.repo.backends.codanna_indexing.try_acquire_backend_index_lock",
                return_value=lease,
            ):
                result = await codanna_indexing._async_run_codanna_full_index(base_dir)

        assert result.status == "lock_error"
        assert result.reason == lease.reason
        assert result.lock_path == lease.lock_path

    def test_second_lease_is_rejected_when_locking_supported(self, tmp_path) -> None:
        if not supports_backend_index_locking():
            pytest.skip("backend index locking is not supported on this platform")

        lease1 = try_acquire_backend_index_lock(str(tmp_path), "chunkhound")
        lease2 = try_acquire_backend_index_lock(str(tmp_path), "chunkhound")
        try:
            assert lease1.acquired is True
            assert lease2.acquired is False
            assert lease2.reason == "lock_held"
            assert lease1.lock_path == lease2.lock_path
        finally:
            lease1.release()
            lease2.release()

    def test_windows_lock_failure_does_not_append_null_byte(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeMsvcrt:
            LK_NBLCK = 1
            LK_UNLCK = 2

            def __init__(self) -> None:
                self.positions: list[int] = []

            def locking(self, fd: int, _mode: int, _nbytes: int) -> None:
                self.positions.append(os.lseek(fd, 0, os.SEEK_CUR))
                raise OSError("already locked")

        fake_msvcrt = FakeMsvcrt()
        monkeypatch.setattr(backend_locking, "fcntl", None)
        monkeypatch.setattr(backend_locking, "msvcrt", fake_msvcrt)

        lock_path = tmp_path / "test.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            with pytest.raises(BlockingIOError):
                backend_locking._lock_handle_nonblocking(handle)

        assert lock_path.read_text(encoding="utf-8") == ""
        assert fake_msvcrt.positions == [0]
