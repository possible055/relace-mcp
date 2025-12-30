import logging
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from ..config.base_dir import invalidate_roots_cache

logger = logging.getLogger(__name__)

ROOTS_LIST_CHANGED_METHOD = "notifications/roots/list_changed"


class RootsMiddleware(Middleware):
    """Middleware to handle MCP Roots notifications.

    Listens for `notifications/roots/list_changed` from the client and
    invalidates the cached base_dir so the next tool call fetches fresh roots.
    """

    async def on_notification(  # dead: disable
        self,
        context: MiddlewareContext[mt.Notification[Any, Any]],
        call_next: CallNext[mt.Notification[Any, Any], Any],
    ) -> Any:
        # MiddlewareContext has a 'method' attribute that contains the notification method name
        if context.method == ROOTS_LIST_CHANGED_METHOD:
            logger.info("[RootsMiddleware] Received roots/list_changed notification")
            invalidate_roots_cache(context.fastmcp_context)

        return await call_next(context)
