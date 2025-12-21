from ....utils import resolve_repo_path


def map_repo_path(path: str, base_dir: str) -> str:
    """Map /repo/... virtual root path to actual filesystem path.

    This function is for INTERNAL use only - translating paths from Relace Search API
    which uses /repo as the virtual repository root.

    External API (fast_apply, fast_search results) now uses absolute paths.

    Args:
        path: Path from Relace API, format: /repo or /repo/...
        base_dir: Actual repo root directory.

    Returns:
        Actual filesystem absolute path.
    """
    try:
        return resolve_repo_path(path, base_dir)
    except ValueError:
        # Fallback: return original path, let validate_file_path handle error
        return path
