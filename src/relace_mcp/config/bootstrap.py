import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_dotenv_from_path() -> Path | None:
    """Load dotenv from MCP_DOTENV_PATH or the default search path."""
    dotenv_path = os.getenv("MCP_DOTENV_PATH", "").strip()
    if dotenv_path:
        path = Path(dotenv_path).expanduser()
        if path.exists():
            load_dotenv(path, override=False)
            logger.debug("Loaded .env from MCP_DOTENV_PATH: %s", path)
            return path

        logger.warning("MCP_DOTENV_PATH does not exist: %s", dotenv_path)
        load_dotenv(override=False)
        return None

    load_dotenv(override=False)
    return None


def reload_runtime_from_env() -> None:
    """Refresh all env-backed runtime settings from the current process env."""
    from . import settings as _settings

    _settings.reload_settings_from_env()


def initialize_runtime_from_env() -> None:
    """Load dotenv first, then refresh the centralized settings module."""
    load_dotenv_from_path()
    reload_runtime_from_env()
