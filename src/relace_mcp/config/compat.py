import logging
import os
import warnings

logger = logging.getLogger(__name__)


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
