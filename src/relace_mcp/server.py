import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from .config import EXPERIMENTAL_LOGGING, LOG_PATH, RelaceConfig
from .tools import register_tools

logger = logging.getLogger(__name__)


def check_health(config: RelaceConfig) -> dict[str, str]:
    results: dict[str, str] = {}
    errors: list[str] = []

    base_dir = Path(config.base_dir)
    if not base_dir.is_dir():
        errors.append(f"base_dir does not exist: {config.base_dir}")
    elif not os.access(base_dir, os.R_OK):
        errors.append(f"base_dir is not readable: {config.base_dir}")
    elif not os.access(base_dir, os.W_OK):
        errors.append(f"base_dir is not writable: {config.base_dir}")
    else:
        results["base_dir"] = "ok"

    if EXPERIMENTAL_LOGGING:
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
