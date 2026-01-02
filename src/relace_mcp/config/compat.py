import logging
import os
import warnings

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}


def getenv_with_fallback(new_name: str, old_name: str, default: str = "") -> str:
    """Get environment variable with deprecation fallback.

    Priority: new_name > old_name > default.
    Emits DeprecationWarning to stderr if old_name is used.
    """
    if (value := os.getenv(new_name)) is not None:
        return value
    if (value := os.getenv(old_name)) is not None:
        warnings.warn(
            f"Environment variable '{old_name}' is deprecated, use '{new_name}' instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        logger.warning(
            "A deprecated environment variable was used; "
            "please update your configuration. See DeprecationWarning for details."
        )
        return value
    return default


def env_bool(name: str, *, default: bool, deprecated_name: str = "") -> bool:
    """Parse environment variable as boolean with fallback to default.

    Recognizes truthy values: 1, true, yes, y, on
    Recognizes falsy values: 0, false, no, n, off
    """
    raw = getenv_with_fallback(name, deprecated_name) if deprecated_name else os.getenv(name)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    warnings.warn(
        f"Invalid boolean env var {name}={raw!r}; defaulting to {default}",
        stacklevel=2,
    )
    logger.warning("Invalid boolean environment variable detected; using default")
    return default
