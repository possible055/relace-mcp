import copy
import json
import logging
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def deep_update_dict(target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_update_dict(target[key], value)
        else:
            target[key] = value
    return target


def _normalize_str_list(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None

    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if stripped:
            values.append(stripped)
    return values


def _read_pyrightconfig(workspace: Path) -> dict[str, Any]:
    path = workspace / "pyrightconfig.json"
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Failed to read pyrightconfig.json: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    analysis: dict[str, Any] = {}
    for key in ("include", "exclude", "ignore"):
        values = _normalize_str_list(data.get(key))
        if values is not None:
            analysis[key] = values

    if not analysis:
        return {}
    return {"basedpyright": {"analysis": analysis}}


def _read_pyproject(workspace: Path) -> dict[str, Any]:
    path = workspace / "pyproject.toml"
    if not path.is_file():
        return {}

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Failed to read pyproject.toml: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}

    section = tool.get("basedpyright")
    if not isinstance(section, dict):
        section = tool.get("pyright")
    if not isinstance(section, dict):
        return {}

    analysis: dict[str, Any] = {}
    for key in ("include", "exclude", "ignore"):
        values = _normalize_str_list(section.get(key))
        if values is not None:
            analysis[key] = values

    if not analysis:
        return {}
    return {"basedpyright": {"analysis": analysis}}


def load_project_workspace_settings(workspace: Path) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    deep_update_dict(settings, _read_pyproject(workspace))
    deep_update_dict(settings, _read_pyrightconfig(workspace))
    return settings


def build_workspace_settings(
    workspace_config: dict[str, Any],
    language_id: str,
    workspace: str,
) -> dict[str, Any]:
    settings = copy.deepcopy(workspace_config)
    if language_id == "python":
        project_settings = load_project_workspace_settings(Path(workspace))
        deep_update_dict(settings, project_settings)
    return settings
