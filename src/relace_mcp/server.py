import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from .config import LOG_PATH, RelaceConfig
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
    else:
        results["base_dir"] = "ok"

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
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    logger.info("Starting Relace MCP Server")
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
