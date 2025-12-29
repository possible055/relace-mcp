"""Tests for RootsMiddleware and roots cache invalidation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.config import base_dir as base_dir_module
from relace_mcp.middleware import roots as roots_module
from relace_mcp.middleware.roots import ROOTS_LIST_CHANGED_METHOD, RootsMiddleware


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

        with patch.object(roots_module, "invalidate_roots_cache") as mock_invalidate:
            result = await middleware.on_notification(context, mock_call_next)

            mock_invalidate.assert_called_once()
            mock_call_next.assert_awaited_once_with(context)
            assert result is None  # call_next returns None

    @pytest.mark.asyncio
    async def test_passes_through_other_notifications(
        self, middleware: RootsMiddleware, mock_call_next: AsyncMock
    ) -> None:
        """Middleware should pass through non-roots notifications without invalidating."""
        context = MagicMock()
        context.method = "notifications/tools/list_changed"

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

        with patch.object(roots_module, "invalidate_roots_cache") as mock_invalidate:
            await middleware.on_notification(context, mock_call_next)

            mock_invalidate.assert_not_called()
            mock_call_next.assert_awaited_once_with(context)


class TestRootsCacheInvalidation:
    """Tests for roots cache invalidation."""

    def test_invalidate_clears_cache(self) -> None:
        """invalidate_roots_cache should clear the cached value."""
        # Set up: populate the cache directly
        base_dir_module._roots_cache = ("/test/path", "MCP Root (test)")
        assert base_dir_module._roots_cache == ("/test/path", "MCP Root (test)")

        # Act: invalidate
        base_dir_module.invalidate_roots_cache()

        # Assert: cache is empty
        assert base_dir_module._roots_cache is None

    def test_cache_is_none_after_invalidation(self) -> None:
        """Cache should be None after invalidation."""
        base_dir_module.invalidate_roots_cache()
        assert base_dir_module._roots_cache is None


class TestResolveBaseDirWithCache:
    """Tests for resolve_base_dir with caching behavior."""

    @pytest.mark.asyncio
    async def test_uses_cache_when_valid(self, tmp_path) -> None:
        """resolve_base_dir should use cached value when available."""
        # Pre-populate cache directly
        cached_path = str(tmp_path / "cached")
        base_dir_module._roots_cache = (cached_path, "MCP Root (cached)")

        ctx = MagicMock()
        ctx.list_roots = AsyncMock()

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(None, ctx)

        assert base_dir == cached_path
        assert source == "MCP Root (cached)"
        ctx.list_roots.assert_not_awaited()

        # Cleanup
        base_dir_module.invalidate_roots_cache()

    @pytest.mark.asyncio
    async def test_fetches_fresh_roots_after_invalidation(self, tmp_path) -> None:
        """After invalidation, resolve_base_dir should fetch fresh roots."""
        # Pre-populate and then invalidate
        base_dir_module._roots_cache = ("/old/path", "MCP Root (old)")
        base_dir_module.invalidate_roots_cache()

        ctx = MagicMock()
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
        base_dir_module._roots_cache = ("/cached/path", "MCP Root (cached)")

        explicit_path = str(tmp_path / "explicit")

        from relace_mcp.config.base_dir import resolve_base_dir

        base_dir, source = await resolve_base_dir(explicit_path, ctx=None)

        from pathlib import Path

        assert base_dir == str(Path(explicit_path).resolve())
        assert source == "RELACE_BASE_DIR"

        # Cleanup
        base_dir_module.invalidate_roots_cache()
