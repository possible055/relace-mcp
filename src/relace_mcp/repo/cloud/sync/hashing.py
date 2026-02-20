import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ...core import compute_file_hash
from .constants import MAX_UPLOAD_WORKERS

logger = logging.getLogger(__name__)


def _compute_file_hashes(
    base_dir: str,
    files: list[str],
) -> dict[str, str]:
    """Compute SHA-256 hashes for files in parallel.

    Args:
        base_dir: Base directory path.
        files: List of relative file paths.

    Returns:
        Dict mapping relative path to "sha256:..." hash.
    """
    hashes: dict[str, str] = {}
    base_path = Path(base_dir).resolve()

    def hash_file(rel_path: str) -> tuple[str, str | None]:
        try:
            file_path = (base_path / rel_path).resolve()
        except (OSError, RuntimeError) as exc:
            logger.debug("Failed to resolve for hash %s: %s", rel_path, exc)
            return (rel_path, None)
        if not file_path.is_relative_to(base_path):
            logger.warning("Blocked path traversal in hash: %s", rel_path)
            return (rel_path, None)
        file_hash = compute_file_hash(file_path)
        return (rel_path, file_hash)

    with ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS) as executor:
        futures = [executor.submit(hash_file, f) for f in files]
        for future in as_completed(futures):
            rel_path, file_hash = future.result()
            if file_hash:
                hashes[rel_path] = file_hash

    return hashes
