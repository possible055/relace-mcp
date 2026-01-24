import os
import random

MCP_LOG_REDACT = os.getenv("MCP_LOG_REDACT", "true").lower() in ("1", "true", "yes")
MCP_LOG_SAMPLE_RATE = float(os.getenv("MCP_LOG_SAMPLE_RATE", "1.0"))


def should_sample() -> bool:
    if MCP_LOG_SAMPLE_RATE >= 1.0:
        return True
    return random.random() < MCP_LOG_SAMPLE_RATE
