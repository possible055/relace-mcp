import argparse
import logging
import os
import sys
import tempfile
import warnings
from dataclasses import replace
from pathlib import Path

# Suppress FastMCP's Rich console output for stdio transport
# This MUST be set BEFORE fastmcp is imported
if "FASTMCP_LOG_LEVEL" not in os.environ:
    os.environ["FASTMCP_LOG_LEVEL"] = "ERROR"

from dotenv import load_dotenv
from fastmcp import FastMCP

from .config import RelaceConfig
from .config.settings import (
    AGENTIC_RETRIEVAL_ENABLED,
    ENCODING_DETECTION_SAMPLE_LIMIT,
    LOG_PATH,
    MCP_LOGGING,
    RETRIEVAL_BACKEND,
)
from .encoding import set_project_encoding
from .middleware import RootsMiddleware, ToolTracingMiddleware
from .tools import register_tools
from .tools.apply.encoding import detect_project_encoding

logger = logging.getLogger(__name__)


def _configure_logging_for_stdio() -> None:
    """Configure logging to avoid stdout pollution in stdio transport mode.

    MCP stdio transport requires clean stdout (JSON-RPC only).
    All logging must go to stderr or file.

    Set MCP_LOG_LEVEL environment variable to control log verbosity:
    - DEBUG: Full diagnostic output (for troubleshooting)
    - INFO: Informational messages
    - WARNING: Only warnings and errors (default)
    - ERROR: Only errors
    """
    # Redirect all warnings to stderr (not stdout)
    warnings.filterwarnings("default")

    # Configure root logger to stderr only
    root = logging.getLogger()
    # Remove any existing handlers that might write to stdout
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Add stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root.addHandler(stderr_handler)

    # Allow user to override log level via environment variable
    level_str = os.getenv("MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_str, logging.WARNING)
    root.setLevel(level)


def _load_dotenv_from_path() -> None:
    """Load .env file from MCP_DOTENV_PATH or default locations.

    Priority:
    1. MCP_DOTENV_PATH environment variable (explicit path)
    2. Default dotenv search (current directory and parents)
    """
    dotenv_path = os.getenv("MCP_DOTENV_PATH", "").strip()
    if dotenv_path:
        path = Path(dotenv_path).expanduser()
        if path.exists():
            load_dotenv(path)
            logger.debug("Loaded .env from MCP_DOTENV_PATH: %s", path)
        else:
            logger.warning("MCP_DOTENV_PATH does not exist: %s", dotenv_path)
            load_dotenv()  # Fallback to default
    else:
        load_dotenv()


def check_health(config: RelaceConfig) -> dict[str, str]:
    results: dict[str, str] = {}
    errors: list[str] = []

    # base_dir is optional; if not set, it will be resolved from MCP Roots at runtime
    if config.base_dir:
        base_dir = Path(config.base_dir)
        if not base_dir.is_dir():
            errors.append(f"base_dir does not exist: {config.base_dir}")
        elif not os.access(base_dir, os.R_OK):
            errors.append(f"base_dir is not readable: {config.base_dir}")
        elif not os.access(base_dir, os.X_OK):
            errors.append(f"base_dir is not traversable: {config.base_dir}")
        elif not os.access(base_dir, os.W_OK):
            warnings.warn(
                f"base_dir is not writable: {config.base_dir}", RuntimeWarning, stacklevel=2
            )
            logger.warning("base_dir is not writable (fast_apply will fail)")
            results["base_dir"] = "read-only (fast_apply disabled)"
        else:
            try:
                with tempfile.NamedTemporaryFile(
                    dir=base_dir, prefix=".relace_healthcheck_", delete=True
                ):
                    pass
            except OSError as exc:
                warnings.warn(f"base_dir tempfile failed: {exc}", RuntimeWarning, stacklevel=2)
                logger.warning("base_dir tempfile failed (fast_apply may fail)")
                results["base_dir"] = "read-only (tempfile failed)"
            else:
                results["base_dir"] = "ok"
    else:
        results["base_dir"] = "deferred (will resolve from MCP Roots)"

    if MCP_LOGGING:
        log_dir = LOG_PATH.parent
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(log_dir, os.W_OK):
                errors.append(f"log directory is not writable: {log_dir}")
            else:
                results["log_path"] = "ok"
        except OSError as exc:
            errors.append(f"cannot create log directory: {exc}")

    # Retrieval backend health check
    if AGENTIC_RETRIEVAL_ENABLED and RETRIEVAL_BACKEND in ("chunkhound", "codanna"):
        from .repo.backends import ExternalCLIError, check_backend_health

        try:
            status = check_backend_health(RETRIEVAL_BACKEND, config.base_dir)
            results["retrieval_backend"] = f"{RETRIEVAL_BACKEND}: {status}"
        except ExternalCLIError as exc:
            if exc.kind == "index_missing" and exc.backend == "chunkhound":
                logger.warning("%s backend: %s — will auto-index on first query", exc.backend, exc)
                results["retrieval_backend"] = f"{RETRIEVAL_BACKEND}: index_missing (deferred)"
            else:
                errors.append(f"{exc.backend} backend: {exc} ({exc.kind})")
    elif AGENTIC_RETRIEVAL_ENABLED and RETRIEVAL_BACKEND == "auto":
        results["retrieval_backend"] = "auto: deferred (resolved at query time)"
    else:
        results["retrieval_backend"] = f"{RETRIEVAL_BACKEND}: ok"

    if errors:
        raise RuntimeError("; ".join(errors))

    return results


def detect_and_set_encoding(config: RelaceConfig) -> RelaceConfig:
    """Detect project encoding and update config.

    If RELACE_DEFAULT_ENCODING is set, use it directly.
    Otherwise, scan project files to auto-detect the dominant encoding.

    Args:
        config: Current configuration.

    Returns:
        Updated configuration with default_encoding set (if detected).
    """
    # If already set via environment, just apply it
    if config.default_encoding:
        logger.debug("Using configured project encoding: %s", config.default_encoding)
        set_project_encoding(config.default_encoding)
        return config

    # Cannot auto-detect encoding without a base_dir
    if not config.base_dir:
        logger.debug("Skipping encoding detection: base_dir not set")
        return config

    # Auto-detect encoding from project files
    base_dir = Path(config.base_dir)
    detected = detect_project_encoding(base_dir, sample_limit=ENCODING_DETECTION_SAMPLE_LIMIT)

    if detected:
        logger.debug("Auto-detected project encoding: %s", detected)
        set_project_encoding(detected)
        # Return updated config with detected encoding
        return replace(config, default_encoding=detected)

    logger.debug("No regional encoding detected, using UTF-8 as default")
    return config


def build_server(config: RelaceConfig | None = None, run_health_check: bool = True) -> FastMCP:
    if config is None:
        config = RelaceConfig.from_env()

    if run_health_check:
        try:
            results = check_health(config)
            logger.debug("Health check passed: %s", results)
        except RuntimeError as exc:
            logger.error("Health check failed: %s", exc)
            raise

    # Detect and set project encoding
    config = detect_and_set_encoding(config)

    mcp = FastMCP("Relace Fast Apply MCP")

    # Register middleware to handle MCP notifications (e.g., roots/list_changed)
    mcp.add_middleware(RootsMiddleware())
    mcp.add_middleware(ToolTracingMiddleware())

    register_tools(mcp, config)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="relace-mcp",
        description="Relace MCP Server - Fast code merging via Relace API",
    )
    parser.add_argument(
        "-t",
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for HTTP mode (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8000,
        help="Port to bind for HTTP mode (default: 8000)",
    )
    parser.add_argument(
        "--path",
        default="/mcp",
        help="MCP endpoint path for HTTP mode (default: /mcp)",
    )
    args = parser.parse_args()

    # stdio-only fixes: must be applied before any output
    if args.transport == "stdio":
        # Fix Windows CRLF issue - Windows converts \n to \r\n, breaking JSON-RPC
        if sys.platform == "win32":
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(newline="\n")
            if hasattr(sys.stdin, "reconfigure"):
                sys.stdin.reconfigure(newline="\n")
        # Configure logging to avoid stdout pollution
        _configure_logging_for_stdio()

    _load_dotenv_from_path()

    config = RelaceConfig.from_env()
    server = build_server(config)

    if args.transport in ("http", "streamable-http"):
        logger.debug(
            "Starting Relace MCP Server (HTTP) on %s:%d%s",
            args.host,
            args.port,
            args.path,
        )
        server.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
            show_banner=False,
        )
    else:
        server.run(show_banner=False)


if __name__ == "__main__":
    main()
