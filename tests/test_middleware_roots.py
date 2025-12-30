"""Tests for RootsMiddleware and roots cache invalidation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.config import base_dir as base_dir_module
from relace_mcp.middleware import roots as roots_module
from relace_mcp.middleware.roots import ROOTS_LIST_CHANGED_METHOD, RootsMiddleware


@pytest.fixture(autouse=True)
def clear_roots_cache():
    base_dir_module.invalidate_roots_cache()
    yield
    base_dir_module.invalidate_roots_cache()


class TestRootsMiddleware:
    """Tests for RootsMiddleware notification handling."""

    @pytest.fixture
    def middleware(self) -> RootsMiddleware:
        return RootsMiddleware()

    @pytest.fixture
    def mock_call_next(self) -> AsyncMock:
        return AsyncMock(return_value=None)

    @pytest.mark.asyncio
    async def test_handles_roots_list_changed_notification(
        self, middleware: RootsMiddleware, mock_call_next: AsyncMock
    ) -> None:
        """Middleware should invalidate cache on roots/list_changed notification."""
        context = MagicMock()
        context.method = ROOTS_LIST_CHANGED_METHOD
        context.fastmcp_context = None

        with patch.object(roots_module, "invalidate_roots_cache") as mock_invalidate:
            result = await middleware.on_notification(context, mock_call_next)

            mock_invalidate.assert_called_once_with(None)
            mock_call_next.assert_awaited_once_with(context)
            assert result is None  # call_next returns None

    @pytest.mark.asyncio
    async def test_handles_roots_list_changed_with_session_context(
        self, middleware: RootsMiddleware, mock_call_next: AsyncMock
    ) -> None:
        """Middleware should pass session context to invalidate_roots_cache."""
        mock_fastmcp_ctx = MagicMock(session_id="test-session-123")
        context = MagicMock()
        context.method = ROOTS_LIST_CHANGED_METHOD
        context.fastmcp_context = mock_fastmcp_ctx

        with patch.object(roots_module, "invalidate_roots_cache") as mock_invalidate:
            await middleware.on_notification(context, mock_call_next)

            mock_invalidate.assert_called_once_with(mock_fastmcp_ctx)

    @pytest.mark.asyncio
    async def test_passes_through_other_notifications(
        self, middleware: RootsMiddleware, mock_call_next: AsyncMock
    ) -> None:
        """Middleware should pass through non-roots notifications without invalidating."""
        context = MagicMock()
        context.method = "notifications/tools/list_changed"
        context.fastmcp_context = None

        with patch.object(roots_module, "invalidate_roots_cache") as mock_invalidate:
            await middleware.on_notification(context, mock_call_next)

            mock_invalidate.assert_not_called()
            mock_call_next.assert_awaited_once_with(context)

    @pytest.mark.asyncio
    async def test_handles_notification_without_method_attr(
        self, middleware: RootsMiddleware, mock_call_next: AsyncMock
    ) -> None:
        """Middleware should gracefully handle notifications without method attribute."""
        context = MagicMock()
        context.method = None  # No method set
        context.fastmcp_context = None

        with patch.object(roots_module, "invalidate_roots_cache") as mock_invalidate:
            await middleware.on_notification(context, mock_call_next)

            mock_invalidate.assert_not_called()
            mock_call_next.assert_awaited_once_with(context)


class TestRootsCacheInvalidation:
    """Tests for roots cache invalidation."""

    def test_invalidate_clears_cache(self) -> None:
        """invalidate_roots_cache should clear the cached value."""
        # Set up: populate the cache directly
        base_dir_module._roots_cache = {"session-1": ("/test/path", "MCP Root (test)")}
        assert base_dir_module._roots_cache == {"session-1": ("/test/path", "MCP Root (test)")}

        # Act: invalidate
        base_dir_module.invalidate_roots_cache()

        # Assert: cache is empty
        assert base_dir_module._roots_cache == {}

    def test_cache_is_none_after_invalidation(self) -> None:
        """Cache should be empty after invalidation."""
        base_dir_module.invalidate_roots_cache()
        assert base_dir_module._roots_cache == {}

    def test_invalidate_clears_only_session_when_context_provided(self) -> None:
        """invalidate_roots_cache(ctx) should only clear the matching session."""
        base_dir_module._roots_cache = {
            "session-1": ("/test/path/1", "MCP Root (1)"),
            "session-2": ("/test/path/2", "MCP Root (2)"),
        }

        ctx = MagicMock(session_id="session-1")
        base_dir_module.invalidate_roots_cache(ctx)

        assert base_dir_module._roots_cache == {"session-2": ("/test/path/2", "MCP Root (2)")}

    def test_invalidate_does_not_touch_session_id_when_request_context_missing(self) -> None:
        """Cache keying should not raise when session_id is unavailable."""

        class CtxNoRequest:
            request_context = None

            @property
            def session_id(self) -> str:
                raise RuntimeError("session_id not available")

            @property
            def client_id(self) -> str:
                return "client-1"

        base_dir_module._roots_cache = {
            "client:client-1": ("/test/path/1", "MCP Root (1)"),
            "session-2": ("/test/path/2", "MCP Root (2)"),
        }

        base_dir_module.invalidate_roots_cache(CtxNoRequest())
        assert base_dir_module._roots_cache == {"session-2": ("/test/path/2", "MCP Root (2)")}


class TestResolveBaseDirWithCache:
    """Tests for resolve_base_dir with caching behavior."""

    @pytest.mark.asyncio
    async def test_uses_cache_when_valid(self, tmp_path) -> None:
        """resolve_base_dir should use cached value when available."""
        # Pre-populate cache directly
        cached_dir = tmp_path / "cached"
        cached_dir.mkdir()
        cached_path = str(cached_dir)
        base_dir_module._roots_cache = {"session-1": (cached_path, "MCP Root (cached)")}

        ctx = MagicMock(session_id="session-1")
        ctx.list_roots = AsyncMock()

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(None, ctx)

        assert base_dir == cached_path
        assert source == "MCP Root (cached)"
        ctx.list_roots.assert_not_awaited()

        # Cleanup
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_clears_invalid_cache_and_refetches_roots(self, tmp_path) -> None:
        """When cached path becomes invalid, clear cache and fetch fresh roots."""
        # Pre-populate cache with a path that will be deleted
        stale_dir = tmp_path / "stale"
        stale_dir.mkdir()
        stale_path = str(stale_dir)
        base_dir_module._roots_cache = {"session-1": (stale_path, "MCP Root (stale)")}

        # Delete the cached directory to make it invalid
        stale_dir.rmdir()

        # Set up fresh roots
        fresh_dir = tmp_path / "fresh"
        fresh_dir.mkdir()

        ctx = MagicMock(session_id="session-1")
        ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{fresh_dir}", name="Fresh Root")]
        )

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(None, ctx)

        # Should have cleared invalid cache and fetched fresh roots
        assert base_dir == str(fresh_dir)
        assert "MCP Root" in source
        ctx.list_roots.assert_awaited_once()

        # Cache should now contain the fresh path
        assert base_dir_module._roots_cache.get("session-1") == (str(fresh_dir), source)

        # Cleanup
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_clears_invalid_cache_and_falls_back_to_git_root(
        self, tmp_path, monkeypatch
    ) -> None:
        """When cached path is invalid and roots also fail, fall back to Git root."""
        # Pre-populate cache with invalid path
        stale_path = str(tmp_path / "does-not-exist")
        base_dir_module._roots_cache = {"session-1": (stale_path, "MCP Root (stale)")}

        # Set up git root
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        cwd = tmp_path / "src"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        ctx = MagicMock(session_id="session-1")
        ctx.list_roots = AsyncMock(return_value=[])  # No roots available

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(None, ctx)

        # Should have cleared invalid cache and fallen back to Git root
        assert base_dir == str(tmp_path)
        assert "Git root" in source
        ctx.list_roots.assert_awaited_once()

        # Invalid cache entry should have been removed
        assert "session-1" not in base_dir_module._roots_cache

        # Cleanup
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_fetches_fresh_roots_after_invalidation(self, tmp_path) -> None:
        """After invalidation, resolve_base_dir should fetch fresh roots."""
        # Pre-populate and then invalidate
        base_dir_module._roots_cache = {"session-1": ("/old/path", "MCP Root (old)")}
        base_dir_module.invalidate_roots_cache()

        ctx = MagicMock(session_id="session-1")
        ctx.list_roots = AsyncMock(
            return_value=[MagicMock(uri=f"file://{tmp_path}", name="Fresh Root")]
        )

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(None, ctx)

        assert base_dir == str(tmp_path)
        assert "MCP Root" in source
        ctx.list_roots.assert_awaited_once()

        # Cleanup
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_explicit_config_bypasses_cache(self, tmp_path) -> None:
        """RELACE_BASE_DIR should bypass both cache and MCP Roots."""
        # Pre-populate cache directly
        base_dir_module._roots_cache = {"session-1": ("/cached/path", "MCP Root (cached)")}

        explicit_path = str(tmp_path / "explicit")

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(explicit_path, ctx=None)

        from pathlib import Path

        assert base_dir == str(Path(explicit_path).resolve())
        assert source == "RELACE_BASE_DIR"

        # Cleanup
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_cache_is_session_scoped(self, tmp_path) -> None:
        """Different sessions should not share cached roots."""
        s1 = tmp_path / "session1"
        s2 = tmp_path / "session2"
        s1.mkdir()
        s2.mkdir()

        base_dir_module._roots_cache = {
            "session-1": (str(s1), "MCP Root (cached 1)"),
            "session-2": (str(s2), "MCP Root (cached 2)"),
        }

        ctx1 = MagicMock(session_id="session-1")
        ctx1.list_roots = AsyncMock()
        ctx2 = MagicMock(session_id="session-2")
        ctx2.list_roots = AsyncMock()

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir_1, source_1 = await resolve_base_dir(None, ctx1)
        base_dir_2, source_2 = await resolve_base_dir(None, ctx2)

        assert base_dir_1 == str(s1)
        assert source_1 == "MCP Root (cached 1)"
        assert base_dir_2 == str(s2)
        assert source_2 == "MCP Root (cached 2)"
        ctx1.list_roots.assert_not_awaited()
        ctx2.list_roots.assert_not_awaited()
