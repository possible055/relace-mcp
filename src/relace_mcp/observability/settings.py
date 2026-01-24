import os
import random

MCP_LOG_REDACT = os.getenv("MCP_LOG_REDACT", "true").lower() in ("1", "true", "yes")


def _parse_sample_rate() -> float:
    raw = os.getenv("MCP_LOG_SAMPLE_RATE", "1.0")
    try:
        return float(raw)
    except ValueError:
        return 1.0


MCP_LOG_SAMPLE_RATE = _parse_sample_rate()


def should_sample() -> bool:
    if MCP_LOG_SAMPLE_RATE >= 1.0:
        return True
    return random.random() < MCP_LOG_SAMPLE_RATE  # nosec B311
