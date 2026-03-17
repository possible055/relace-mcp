import asyncio
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

    from ..config import RelaceConfig

logger = logging.getLogger(__name__)


class EncodingState:
    """Tracks per-process encoding detection for the ctx=None (no-session) path."""

    def __init__(self) -> None:
        self._done = False
        self._lock = threading.Lock()

    @property
    def done(self) -> bool:
        return self._done

    def mark_done(self) -> None:
        with self._lock:
            self._done = True


async def ensure_encoding_detected(
    config: "RelaceConfig",
    ctx: "Context | None",
    resolved_base_dir: str,
    state: EncodingState,
) -> None:
    """Detect and apply project encoding if not already done.

    Args:
        config: Relace configuration (may supply default_encoding).
        ctx: MCP context, or None for sessionless calls.
        resolved_base_dir: Resolved absolute base directory path.
        state: Per-register_tools encoding done state.
    """
    if ctx is None:
        if state.done:
            return

        base = resolved_base_dir or config.base_dir
        if not base:
            return

        from ..config.settings import ENCODING_DETECTION_SAMPLE_LIMIT
        from ..encoding import detect_project_encoding, set_project_encoding

        if config.default_encoding:
            logger.debug("Using configured project encoding: %s", config.default_encoding)
            set_project_encoding(config.default_encoding)
            state.mark_done()
            return

        detected = await asyncio.to_thread(
            detect_project_encoding,
            Path(base),
            sample_limit=ENCODING_DETECTION_SAMPLE_LIMIT,
        )
        if detected:
            logger.debug("Auto-detected project encoding: %s", detected)
            set_project_encoding(detected)
        else:
            logger.debug("No regional encoding detected, using UTF-8 as default")

        state.mark_done()
        return

    base_dir_key = "relace.encoding.base_dir"
    done_key = "relace.encoding.done"

    prev_base_dir = (await ctx.get_state(base_dir_key)) or ""
    if prev_base_dir != resolved_base_dir:
        await ctx.set_state(base_dir_key, resolved_base_dir)
        await ctx.set_state(done_key, False)

    if await ctx.get_state(done_key):
        return

    from ..config.settings import ENCODING_DETECTION_SAMPLE_LIMIT
    from ..encoding import detect_project_encoding, set_project_encoding

    if config.default_encoding:
        logger.debug("Using configured project encoding: %s", config.default_encoding)
        set_project_encoding(config.default_encoding)
    else:
        detected = await asyncio.to_thread(
            detect_project_encoding,
            Path(resolved_base_dir),
            sample_limit=ENCODING_DETECTION_SAMPLE_LIMIT,
        )
        if detected:
            logger.debug("Auto-detected project encoding: %s", detected)
            set_project_encoding(detected)
        else:
            logger.debug("No regional encoding detected, using UTF-8 as default")

    await ctx.set_state(done_key, True)


__all__: list[Any] = ["EncodingState", "ensure_encoding_detected"]
