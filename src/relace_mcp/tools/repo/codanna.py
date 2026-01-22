import json
import os
import subprocess
from typing import Any


def codanna_search(
    query: str, *, base_dir: str, limit: int = 8, threshold: float = 0.3
) -> list[dict[str, Any]]:
    """Run codanna MCP CLI search.

    Args:
        query: Search query text.
        base_dir: Repository base directory.
        limit: Maximum number of results to return.
        threshold: Minimum similarity threshold.

    Returns:
        List of dicts with filename and score keys.

    Raises:
        RuntimeError: When the codanna CLI fails or JSON parsing fails.
    """
    command = [
        "codanna",
        "mcp",
        "semantic_search_with_context",
        f"query:{query}",
        f"limit:{limit}",
        f"threshold:{threshold}",
        "--json",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": base_dir,
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"codanna CLI failed: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"codanna CLI error (exit {result.returncode}): {stderr}")

    payload = (result.stdout or "").strip()
    if not payload:
        return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"codanna JSON parse error: {exc}") from exc

    items = data.get("results") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename") or item.get("path") or item.get("file")
        score = item.get("score")
        if not filename:
            continue
        try:
            score_val = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_val = 0.0
        results.append({"filename": filename, "score": score_val})

    return results
