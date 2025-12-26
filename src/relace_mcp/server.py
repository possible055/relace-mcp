import argparse
import logging
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from .config import RelaceConfig
from .config.settings import ENCODING_DETECTION_SAMPLE_LIMIT, LOG_PATH, RELACE_LOGGING
from .tools import register_tools
from .tools.apply.encoding import detect_project_encoding
from .tools.apply.file_io import set_project_encoding

logger = logging.getLogger(__name__)


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
            errors.append(f"base_dir is not writable: {config.base_dir}")
        else:
            try:
                with tempfile.NamedTemporaryFile(
                    dir=base_dir, prefix=".relace_healthcheck_", delete=True
                ):
                    pass
            except OSError as exc:
                errors.append(f"base_dir is not writable (tempfile failed): {exc}")
            else:
                results["base_dir"] = "ok"
    else:
        results["base_dir"] = "deferred (will resolve from MCP Roots)"

    if RELACE_LOGGING:
        log_dir = LOG_PATH.parent
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(log_dir, os.W_OK):
                errors.append(f"log directory is not writable: {log_dir}")
            else:
                results["log_path"] = "ok"
        except OSError as exc:
            errors.append(f"cannot create log directory: {exc}")

    if not config.api_key.startswith("rlc-"):
        logger.warning("API key does not start with 'rlc-', may be invalid")
        results["api_key_format"] = "warning"
    else:
        results["api_key_format"] = "ok"

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
        logger.info("Using configured project encoding: %s", config.default_encoding)
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
        logger.info("Auto-detected project encoding: %s", detected)
        set_project_encoding(detected)
        # Return updated config with detected encoding
        return replace(config, default_encoding=detected)

    logger.info("No regional encoding detected, using UTF-8 as default")
    return config


def build_server(config: RelaceConfig | None = None, run_health_check: bool = True) -> FastMCP:
    if config is None:
        config = RelaceConfig.from_env()

    if run_health_check:
        try:
            results = check_health(config)
            logger.info("Health check passed: %s", results)
        except RuntimeError as exc:
            logger.error("Health check failed: %s", exc)
            raise

    # Detect and set project encoding
    config = detect_and_set_encoding(config)

    mcp = FastMCP("Relace Fast Apply MCP")
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
        default="0.0.0.0",  # nosec B104
        help="Host to bind for HTTP mode (default: 0.0.0.0)",
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

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    config = RelaceConfig.from_env()
    server = build_server(config)

    if args.transport in ("http", "streamable-http"):
        logger.info(
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
        )
    else:
        logger.info("Starting Relace MCP Server (STDIO)")
        server.run()


if __name__ == "__main__":
    main()
