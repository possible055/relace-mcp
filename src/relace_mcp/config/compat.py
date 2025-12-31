import logging
import os
import warnings

logger = logging.getLogger(__name__)


def getenv_with_fallback(new_name: str, old_name: str, default: str = "") -> str:
    """Get environment variable with deprecation fallback.

    Priority: new_name > old_name > default.
    Emits DeprecationWarning to stderr if old_name is used.
    """
    if value := os.getenv(new_name):
        return value
    if value := os.getenv(old_name):
        warnings.warn(
            f"Environment variable '{old_name}' is deprecated, use '{new_name}' instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        logger.warning("Deprecated env var '%s' used, migrate to '%s'", old_name, new_name)
        return value
    return default
