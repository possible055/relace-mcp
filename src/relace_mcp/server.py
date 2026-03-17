import argparse
import logging
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from .config import RelaceConfig

logger = logging.getLogger(__name__)


def _ensure_fastmcp_log_level() -> None:
    # Suppress FastMCP's Rich console output for stdio transport.
    # This MUST be set BEFORE fastmcp is imported.
    os.environ.setdefault("FASTMCP_LOG_LEVEL", "ERROR")


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
    from .config import settings as _settings

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

    level = getattr(logging, _settings.MCP_LOG_LEVEL, logging.WARNING)
    root.setLevel(level)


def _load_dotenv_from_path() -> None:
    """Compatibility wrapper for shared runtime bootstrap dotenv loading."""
    from .config.bootstrap import load_dotenv_from_path

    load_dotenv_from_path()


def check_health(config: "RelaceConfig") -> dict[str, str]:
    from .config import settings as _settings

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

    if _settings.MCP_LOGGING:
        log_dir = _settings.LOG_PATH.parent
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(log_dir, os.W_OK):
                errors.append(f"log directory is not writable: {log_dir}")
            else:
                results["log_path"] = "ok"
        except OSError as exc:
            errors.append(f"cannot create log directory: {exc}")

    if _settings.MCP_TRACE_LOGGING:
        trace_dir = _settings.TRACE_PATH.parent
        try:
            trace_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(trace_dir, os.W_OK):
                errors.append(f"trace directory is not writable: {trace_dir}")
            else:
                results["trace_path"] = "ok"
        except OSError as exc:
            errors.append(f"cannot create trace directory: {exc}")

    # Retrieval backend health check (passive only: do NOT run expensive CLI probes on startup)
    if _settings.AGENTIC_RETRIEVAL_ENABLED and _settings.RETRIEVAL_BACKEND in (
        "chunkhound",
        "codanna",
    ):
        cli_path = shutil.which(_settings.RETRIEVAL_BACKEND)
        if not cli_path:
            logger.warning(
                "%s backend: CLI not found in PATH — retrieval will be unavailable until installed",
                _settings.RETRIEVAL_BACKEND,
            )
            results["retrieval_backend"] = f"{_settings.RETRIEVAL_BACKEND}: cli_not_found"
        elif not config.base_dir:
            results["retrieval_backend"] = (
                f"{_settings.RETRIEVAL_BACKEND}: deferred (base_dir not set)"
            )
        else:
            results["retrieval_backend"] = f"{_settings.RETRIEVAL_BACKEND}: cli_found"
    elif _settings.AGENTIC_RETRIEVAL_ENABLED and _settings.RETRIEVAL_BACKEND == "auto":
        results["retrieval_backend"] = "auto: deferred (resolved at query time)"
    else:
        results["retrieval_backend"] = f"{_settings.RETRIEVAL_BACKEND}: ok"

    if errors:
        raise RuntimeError("; ".join(errors))

    return results


def build_server(
    config: "RelaceConfig | None" = None,
    run_health_check: bool = True,
) -> "FastMCP":
    _ensure_fastmcp_log_level()

    from fastmcp import FastMCP

    from .config import RelaceConfig
    from .config import settings as _settings
    from .config.bootstrap import initialize_runtime_from_env
    from .middleware import (
        CloudVisibilityMiddleware,
        ProgressHeartbeatMiddleware,
        RootsMiddleware,
        ToolTracingMiddleware,
    )
    from .tools import register_tools

    initialize_runtime_from_env()

    if config is None:
        config = RelaceConfig.from_env()

    if run_health_check:
        try:
            results = check_health(config)
            logger.debug("Health check passed: %s", results)
        except RuntimeError as exc:
            logger.error("Health check failed: %s", exc)
            raise

    mcp = FastMCP("Relace Fast Apply MCP")

    # Register middleware to handle MCP notifications (e.g., roots/list_changed)
    mcp.add_middleware(RootsMiddleware())
    mcp.add_middleware(CloudVisibilityMiddleware(cloud_tools_enabled=_settings.RELACE_CLOUD_TOOLS))
    mcp.add_middleware(ProgressHeartbeatMiddleware())
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

    from .config import RelaceConfig
    from .config import settings as _settings
    from .config.bootstrap import initialize_runtime_from_env
    from .observability import log_event

    initialize_runtime_from_env()
    _ensure_fastmcp_log_level()

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

    if _settings.MCP_LOGGING_MODE == "full":
        logger.warning(
            "MCP_LOGGING=full: writing unredacted tool/LLM I/O to %s and %s.",
            _settings.LOG_PATH,
            _settings.TRACE_PATH,
        )

    config = RelaceConfig.from_env()
    try:
        server_start_event: dict[str, object] = {
            "kind": "server_start",
            "level": "info",
            "transport": args.transport,
            "mcp_log_level": _settings.MCP_LOG_LEVEL,
            "mcp_logging_mode": _settings.MCP_LOGGING_MODE,
            "mcp_trace_enabled": _settings.MCP_TRACE_LOGGING,
            "log_path": str(_settings.LOG_PATH),
            "trace_path": str(_settings.TRACE_PATH),
            "relace_cloud_tools": _settings.RELACE_CLOUD_TOOLS,
            "mcp_search_retrieval": _settings.AGENTIC_RETRIEVAL_ENABLED,
            "mcp_retrieval_backend": _settings.RETRIEVAL_BACKEND,
            "codanna_cli_found": bool(shutil.which("codanna")),
            "chunkhound_cli_found": bool(shutil.which("chunkhound")),
            "base_dir": config.base_dir,
        }

        log_event(server_start_event)
    except Exception:
        # Startup logging must never break MCP stdio transport.
        logger.debug("Failed to write server_start event", exc_info=True)
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
