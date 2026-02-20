import logging
import shutil

from .chunkhound import _chunkhound_health_probe
from .codanna import _codanna_health_probe
from .errors import ExternalCLIError

logger = logging.getLogger(__name__)


def check_backend_health(backend: str, base_dir: str | None) -> str:
    """Validate that an external CLI backend is usable.

    Returns:
        Status string: "ok", or "deferred (base_dir not set)".

    Raises:
        ExternalCLIError: If the CLI is missing or the index is unavailable.
    """
    if backend not in ("chunkhound", "codanna"):
        return "ok"

    cli_name = backend
    if not shutil.which(cli_name):
        raise ExternalCLIError(
            backend=backend,
            kind="cli_not_found",
            message=f"{cli_name} CLI not found in PATH. Install with: pip install {cli_name}",
        )

    if not base_dir:
        return "deferred (base_dir not set)"

    if backend == "chunkhound":
        _chunkhound_health_probe(base_dir)
    elif backend == "codanna":
        _codanna_health_probe(base_dir)

    return "ok"
