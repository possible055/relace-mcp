import logging
import os
from pathlib import Path

import httpx
from fastmcp import FastMCP

from .config import RelaceConfig
from .tools import register_tools

logger = logging.getLogger(__name__)


def check_health(config: RelaceConfig, ping_api: bool = False) -> dict[str, str]:
    """執行健康檢查。

    Args:
        config: Relace 設定。
        ping_api: 是否 ping Relace API endpoint。

    Returns:
        檢查結果 dict。

    Raises:
        RuntimeError: 若任一檢查失敗。
    """
    results: dict[str, str] = {}
    errors: list[str] = []

    # 1. 檢查 base_dir 存在且可存取
    base_dir = Path(config.base_dir)
    if not base_dir.is_dir():
        errors.append(f"base_dir does not exist: {config.base_dir}")
    elif not os.access(base_dir, os.R_OK):
        errors.append(f"base_dir is not readable: {config.base_dir}")
    else:
        results["base_dir"] = "ok"

    # 2. 檢查 log_path 父目錄可寫
    log_path = Path(config.log_path)
    log_dir = log_path.parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(log_dir, os.W_OK):
            errors.append(f"log directory is not writable: {log_dir}")
        else:
            results["log_path"] = "ok"
    except OSError as exc:
        errors.append(f"cannot create log directory: {exc}")

    # 3. 檢查 API key 格式
    if not config.api_key.startswith("rlc-"):
        logger.warning("API key does not start with 'rlc-', may be invalid")
        results["api_key_format"] = "warning"
    else:
        results["api_key_format"] = "ok"

    # 4. 可選：ping Relace API
    if ping_api:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.head(config.endpoint)
                if resp.status_code < 500:
                    results["api_ping"] = "ok"
                else:
                    errors.append(f"API ping failed: status {resp.status_code}")
        except httpx.RequestError as exc:
            errors.append(f"API ping failed: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))

    return results


def build_server(config: RelaceConfig | None = None, run_health_check: bool = True) -> FastMCP:
    """建立並設定 FastMCP 實例。

    Args:
        config: Relace 設定，若為 None 則從環境變數載入。
        run_health_check: 是否在啟動時執行健康檢查。

    Returns:
        已註冊 tools 的 FastMCP 實例。
    """
    if config is None:
        config = RelaceConfig.from_env()

    if run_health_check:
        try:
            results = check_health(config, ping_api=False)
            logger.info("Health check passed: %s", results)
        except RuntimeError as exc:
            logger.error("Health check failed: %s", exc)
            if config.strict_mode:
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

    log_level_str = os.getenv("RELACE_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    logger.info("Starting Relace MCP Server (log_level=%s)", log_level_str)
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
