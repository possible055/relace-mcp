# pyright: reportUnusedFunction=false
import logging
from pathlib import Path
from typing import Any

from ..core import SyncState
from ._sync_files import _decode_file_content, _read_file_content

logger = logging.getLogger(__name__)


def _compute_diff_operations(
    base_dir: str,
    current_files: dict[str, str],
    cached_state: SyncState | None,
) -> tuple[list[dict[str, Any]], dict[str, str], set[str]]:
    """Compute diff operations between current files and cached state.

    Args:
        base_dir: Base directory path.
        current_files: Dict mapping relative path to hash.
        cached_state: Previous sync state, or None for full sync.

    Returns:
        Tuple of (operations list, new file hashes, skipped files set).
    """
    operations: list[dict[str, Any]] = []
    new_hashes: dict[str, str] = {}
    new_skipped: set[str] = set()

    cached_files = cached_state.files if cached_state else {}
    cached_skipped = cached_state.skipped_files if cached_state else set()

    for rel_path, current_hash in current_files.items():
        cached_hash = cached_files.get(rel_path)
        was_skipped = rel_path in cached_skipped

        if cached_hash != current_hash or was_skipped:
            content = _read_file_content(base_dir, rel_path)
            if content is not None:
                content_str = _decode_file_content(content, path=Path(base_dir) / rel_path)
                if content_str is None:
                    logger.debug("Skipping binary file: %s", rel_path)
                    new_hashes[rel_path] = current_hash
                    new_skipped.add(rel_path)
                    continue
                operations.append(
                    {
                        "type": "write",
                        "filename": rel_path,
                        "content": content_str,
                    }
                )
                new_hashes[rel_path] = current_hash
            else:
                new_hashes[rel_path] = current_hash
                new_skipped.add(rel_path)
        else:
            new_hashes[rel_path] = current_hash

    for rel_path in cached_files:
        if rel_path not in current_files:
            file_path = Path(base_dir) / rel_path
            if file_path.exists():
                logger.warning("Skipping delete for %s: file exists but hash failed", rel_path)
                continue
            operations.append(
                {
                    "type": "delete",
                    "filename": rel_path,
                }
            )

    return operations, new_hashes, new_skipped
