import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

import relace_mcp.background_index_monitor as bgmon
import relace_mcp.repo.backends.chunkhound as chunkhound_backend
import relace_mcp.repo.backends.codanna_indexing as codanna_indexing
from relace_mcp.background_index_monitor import BackgroundIndexMonitor
from relace_mcp.config import RelaceConfig
from relace_mcp.repo.backends.locking import (
    BackendIndexLease,
    BackendIndexRunResult,
    supports_backend_index_locking,
    try_acquire_backend_index_lock,
)
from relace_mcp.repo.freshness import FreshnessStatus


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

        with patch(
            "relace_mcp.background_index_monitor.shutil.which", return_value="/usr/bin/fake"
        ):
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
            "relace_mcp.background_index_monitor.shutil.which",
            side_effect=lambda name: (
                f"/usr/bin/{name}" if name in {"codanna", "chunkhound"} else None
            ),
        ):
            backend, reason = monitor._resolve_startup_state()

        assert backend == "codanna"
        assert reason == "ok"

        monitor._active_backend = backend
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
            patch("relace_mcp.background_index_monitor.shutil.which", return_value="/usr/bin/fake"),
            patch.object(bgmon, "_async_run_codanna_full_index", AsyncMock()) as mock_codanna,
            patch.object(bgmon, "_async_run_chunkhound_index", AsyncMock()) as mock_chunkhound,
        ):
            mock_codanna.return_value = BackendIndexRunResult(status="completed")
            result = await monitor._tick()

        assert result.status == "completed"
        mock_codanna.assert_awaited_once_with(str(tmp_path))
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
            patch("relace_mcp.background_index_monitor.asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await monitor._run_loop()

        assert delays == [1, 60.0]

    @pytest.mark.asyncio
    async def test_cli_missing_logs_warning_once(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _configure_monitor_settings(monkeypatch, retrieval_backend="chunkhound")
        monitor = BackgroundIndexMonitor(RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path)))
        monitor._active_backend = "chunkhound"

        caplog.set_level(logging.WARNING)
        with patch("relace_mcp.background_index_monitor.shutil.which", return_value=None):
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
