"""Tests for cloud_status MCP resource with MCP Roots resolution."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.tools.repo.state import SyncState


class TestCloudStatusLogic:
    """Test cloud_status resource logic with MCP Roots dynamic resolution."""

    @pytest.fixture
    def sample_sync_state(self) -> SyncState:
        return SyncState(
            repo_id="test-repo-id",
            repo_name="test-repo",
            repo_head="head123",
            last_sync="2025-01-15T00:00:00Z",
            git_branch="main",
            git_head_sha="abc123def456789012345678901234567890",
            files={"main.py": "sha256:abc", "utils.py": "sha256:def"},
        )

    @pytest.fixture(autouse=True)
    def clear_roots_cache(self) -> Iterator[None]:
        """Clear roots cache before and after each test."""
        from relace_mcp.config import base_dir as base_dir_module

        base_dir_module.invalidate_roots_cache()
        yield
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_cloud_status_resolves_base_dir_from_mcp_roots(self, tmp_path: Path) -> None:
        """cloud_status should use resolve_base_dir to get base_dir from MCP Roots."""
        from relace_mcp.config import resolve_base_dir

        # Mock context with MCP Roots
        mock_ctx = MagicMock()
        mock_ctx.session_id = "test-session"
        mock_ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{tmp_path}", name="Test Root")]
        )

        # Simulate what cloud_status does
        base_dir, source = await resolve_base_dir(None, mock_ctx)

        assert base_dir == str(tmp_path)
        assert "MCP Root" in source

    @pytest.mark.asyncio
    async def test_cloud_status_falls_back_to_cwd_when_no_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no roots available, resolve_base_dir falls back to cwd with warning."""
        from relace_mcp.config import resolve_base_dir

        mock_ctx = MagicMock()
        mock_ctx.session_id = "test-session"
        mock_ctx.list_roots = AsyncMock(return_value=[])

        # Change to tmp_path which has no .git
        monkeypatch.chdir(tmp_path)

        # Should not raise, falls back to cwd
        base_dir, source = await resolve_base_dir(None, mock_ctx)

        assert base_dir == str(tmp_path)
        assert "cwd" in source.lower() or "fallback" in source.lower()

    @pytest.mark.asyncio
    async def test_cloud_status_uses_explicit_base_dir(self, tmp_path: Path) -> None:
        """cloud_status should use explicit base_dir when configured, bypassing MCP Roots."""
        from relace_mcp.config import resolve_base_dir

        # No context needed when base_dir is explicit
        base_dir, source = await resolve_base_dir(str(tmp_path), ctx=None)

        assert base_dir == str(tmp_path.resolve())
        assert source == "MCP_BASE_DIR"

    @pytest.mark.asyncio
    async def test_cloud_status_returns_not_synced_when_no_state(self, tmp_path: Path) -> None:
        """cloud_status should return not synced message when no sync state exists."""
        from relace_mcp.tools.repo.state import load_sync_state

        # Simulate cloud_status logic when state is None
        repo_name = tmp_path.name
        state = load_sync_state(repo_name)

        # No sync state should exist for random tmp_path
        assert state is None

        # This is what cloud_status returns in this case
        message = "No sync state found. Run cloud_sync to upload codebase."
        result = {
            "synced": False,
            "repo_name": repo_name,
            "message": message,
        }

        assert result["synced"] is False
        assert "No sync state found" in message

    @pytest.mark.asyncio
    async def test_cloud_status_builds_correct_response(
        self, tmp_path: Path, sample_sync_state: SyncState
    ) -> None:
        """Test cloud_status response building with sync state."""
        from relace_mcp.tools.repo import state as state_module

        repo_name = tmp_path.name

        with patch.object(state_module, "load_sync_state", return_value=sample_sync_state):
            state = state_module.load_sync_state(repo_name)

        assert state is not None
        assert state.repo_id == "test-repo-id"

        # Build result like cloud_status does
        result = {
            "synced": True,
            "repo_id": state.repo_id,
            "repo_name": state.repo_name or repo_name,
            "git_ref": (
                f"{state.git_branch}@{state.git_head_sha[:8]}"
                if state.git_branch and state.git_head_sha
                else state.git_head_sha[:8]
                if state.git_head_sha
                else ""
            ),
            "files_count": len(state.files),
            "last_sync": state.last_sync,
        }

        assert result["synced"] is True
        assert result["repo_id"] == "test-repo-id"
        assert result["files_count"] == 2
        assert result["git_ref"] == "main@abc123de"

    @pytest.mark.asyncio
    async def test_cloud_status_caches_roots_per_session(self, tmp_path: Path) -> None:
        """cloud_status should cache resolved roots per session."""
        from relace_mcp.config import resolve_base_dir

        mock_ctx = MagicMock()
        mock_ctx.session_id = "test-session-cache"
        mock_ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{tmp_path}", name="Test Root")]
        )

        # First call should call list_roots
        base_dir1, _ = await resolve_base_dir(None, mock_ctx)
        mock_ctx.list_roots.assert_awaited_once()

        # Second call should use cache
        mock_ctx.list_roots.reset_mock()
        base_dir2, _ = await resolve_base_dir(None, mock_ctx)
        mock_ctx.list_roots.assert_not_awaited()

        assert base_dir1 == base_dir2

    @pytest.mark.asyncio
    async def test_cloud_status_invalidates_cache_correctly(self, tmp_path: Path) -> None:
        """Invalidating cache should cause fresh roots fetch."""
        from relace_mcp.config import base_dir as base_dir_module
        from relace_mcp.config import resolve_base_dir

        mock_ctx = MagicMock()
        mock_ctx.session_id = "test-session-invalidate"
        mock_ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{tmp_path}", name="Test Root")]
        )

        # First call
        await resolve_base_dir(None, mock_ctx)
        mock_ctx.list_roots.assert_awaited_once()

        # Invalidate cache
        base_dir_module.invalidate_roots_cache(mock_ctx)

        # Next call should fetch again
        mock_ctx.list_roots.reset_mock()
        await resolve_base_dir(None, mock_ctx)
        mock_ctx.list_roots.assert_awaited_once()
