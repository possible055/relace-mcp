import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 預設 log 路徑
DEFAULT_LOG_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
    "relace",
)
DEFAULT_LOG_PATH = os.path.join(DEFAULT_LOG_DIR, "relace_apply.log")

# Log 檔案大小上限（10MB）
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class RelaceConfig:
    api_key: str
    endpoint: str
    model: str
    log_path: str
    timeout: float
    base_dir: str
    strict_mode: bool
    max_retries: int
    retry_base_delay: float

    @classmethod
    def from_env(cls) -> "RelaceConfig":
        api_key = os.getenv("RELACE_API_KEY")
        if not api_key:
            raise RuntimeError("RELACE_API_KEY is not set. Please export it in your environment.")

        # timeout 預設 60 秒，大型檔案合併需要更長時間
        timeout_str = os.getenv("RELACE_TIMEOUT", "60.0")
        try:
            timeout = float(timeout_str)
            if timeout <= 0:
                raise ValueError("timeout must be positive")
        except ValueError:
            timeout = 60.0

        # base_dir 用於限制檔案存取範圍
        # 若未設定，預設為當前工作目錄並發出警告
        base_dir = os.getenv("RELACE_BASE_DIR")
        if base_dir:
            base_dir = os.path.abspath(base_dir)
        else:
            base_dir = os.getcwd()
            logger.warning(
                "RELACE_BASE_DIR not set. Defaulting to current directory: %s. "
                "For production, explicitly set RELACE_BASE_DIR to restrict file access.",
                base_dir,
            )

        # 驗證 base_dir 存在且可存取
        if not os.path.isdir(base_dir):
            raise RuntimeError(f"RELACE_BASE_DIR does not exist or is not a directory: {base_dir}")

        # log_path 預設使用絕對路徑
        log_path = os.getenv("RELACE_LOG_PATH", DEFAULT_LOG_PATH)
        if not os.path.isabs(log_path):
            log_path = os.path.abspath(log_path)
            logger.warning(
                "RELACE_LOG_PATH is a relative path, resolved to: %s. "
                "Consider using an absolute path for production.",
                log_path,
            )

        # strict_mode：若為 true，則 base_dir 未設定時直接拒絕啟動
        strict_mode = os.getenv("RELACE_STRICT_MODE", "").lower() in ("1", "true", "yes")
        if strict_mode and not os.getenv("RELACE_BASE_DIR"):
            raise RuntimeError(
                "RELACE_STRICT_MODE is enabled but RELACE_BASE_DIR is not set. "
                "Please set RELACE_BASE_DIR to restrict file access."
            )

        # retry 設定
        max_retries_str = os.getenv("RELACE_MAX_RETRIES", "3")
        try:
            max_retries = int(max_retries_str)
            if max_retries < 0:
                max_retries = 3
        except ValueError:
            max_retries = 3

        retry_base_delay_str = os.getenv("RELACE_RETRY_BASE_DELAY", "1.0")
        try:
            retry_base_delay = float(retry_base_delay_str)
            if retry_base_delay <= 0:
                retry_base_delay = 1.0
        except ValueError:
            retry_base_delay = 1.0

        return cls(
            api_key=api_key,
            endpoint=os.getenv(
                "RELACE_ENDPOINT",
                "https://instantapply.endpoint.relace.run/v1/code/apply",
            ),
            model=os.getenv("RELACE_MODEL", "relace-apply-3"),
            log_path=log_path,
            timeout=timeout,
            base_dir=base_dir,
            strict_mode=strict_mode,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
        )
