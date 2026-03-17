from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ._clients import ToolClients
from ._setup import EncodingState, ensure_encoding_detected

if TYPE_CHECKING:
    from fastmcp.server.context import Context

    from ..config import RelaceConfig


def read_text_safe(path: Path) -> str | None:
    """Read text from *path*, returning ``None`` for symlinks, missing, or empty files."""
    try:
        if path.is_symlink():
            return None
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return text or None
    except OSError:
        return None


@dataclass(slots=True)
class ToolRegistryDeps:
    config: "RelaceConfig"
    clients: ToolClients
    encoding_state: EncodingState

    async def ensure_encoding(self, ctx: "Context | None", resolved_base_dir: str) -> None:
        await ensure_encoding_detected(self.config, ctx, resolved_base_dir, self.encoding_state)
