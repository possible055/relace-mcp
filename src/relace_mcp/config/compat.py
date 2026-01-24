import os
import warnings

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}


def env_bool(name: str, *, default: bool) -> bool:
    """Parse environment variable as boolean with fallback to default.

    Recognizes truthy values: 1, true, yes, y, on
    Recognizes falsy values: 0, false, no, n, off
    """
    raw = os.getenv(name)
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
    return default
