import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def _run_cli_json(
    command: list[str], base_dir: str, timeout: int, env: dict[str, str] | None = None
) -> Any:
    if env is None:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", base_dir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }

    try:
        result = subprocess.run(
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI timeout after {timeout}s: {exc}") from exc
    except FileNotFoundError as exc:
        cmd_name = command[0] if command else "unknown"
        raise RuntimeError(f"{cmd_name} CLI not found: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"CLI failed: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        cmd_name = command[0] if command else "CLI"
        raise RuntimeError(f"{cmd_name} error (exit {result.returncode}): {stderr}")

    payload = (result.stdout or "").strip()
    if not payload:
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON parse error: {exc}") from exc


def chunkhound_search(
    query: str, *, base_dir: str, limit: int = 8, threshold: float = 0.3, _retry: bool = False
) -> list[dict[str, Any]]:
    env = os.environ.copy()
    env["HOME"] = os.environ.get("HOME", base_dir)
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"

    command = ["chunkhound", "search", query, "--limit", str(limit), "--json"]

    try:
        data = _run_cli_json(command, base_dir, timeout=120, env=env)
    except RuntimeError as exc:
        if "not found" in str(exc):
            raise RuntimeError(
                "chunkhound CLI not found. Install with: pip install chunkhound"
            ) from exc
        stderr = str(exc)
        if "not indexed" in stderr.lower() or "no index" in stderr.lower():
            if _retry:
                raise RuntimeError(
                    "ChunkHound index creation failed or index still not found"
                ) from exc
            logger.info("ChunkHound index not found, attempting to create...")
            _ensure_chunkhound_index(base_dir, env)
            return chunkhound_search(
                query, base_dir=base_dir, limit=limit, threshold=threshold, _retry=True
            )
        raise

    if data is None:
        return []

    return _parse_chunkhound_results(data, threshold)


def _ensure_chunkhound_index(base_dir: str, env: dict[str, str]) -> None:
    command = ["chunkhound", "index"]
    try:
        result = subprocess.run(
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env=env,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"chunkhound index failed: {stderr}")
        logger.info("ChunkHound index created successfully")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"chunkhound index timeout: {exc}") from exc


def _parse_chunkhound_results(data: Any, threshold: float) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        items = data.get("results") or data.get("chunks") or []
    elif isinstance(data, list):
        items = data
    else:
        return []

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        filename = (
            item.get("file_path") or item.get("filename") or item.get("path") or item.get("file")
        )
        score = item.get("similarity_score") or item.get("score")

        if not filename:
            continue

        try:
            score_val = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_val = 0.0

        if score_val < threshold:
            continue

        results.append({"filename": filename, "score": score_val})

    return results


def codanna_search(
    query: str, *, base_dir: str, limit: int = 8, threshold: float = 0.3
) -> list[dict[str, Any]]:
    command = [
        "codanna",
        "mcp",
        "semantic_search_with_context",
        f"query:{query}",
        f"limit:{limit}",
        f"threshold:{threshold}",
        "--json",
    ]

    data = _run_cli_json(command, base_dir, timeout=60)
    if data is None:
        return []

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
