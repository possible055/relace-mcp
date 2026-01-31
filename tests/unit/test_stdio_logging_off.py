import json
import logging
import os
import subprocess
import sys
from pathlib import Path


def test_mcp_log_level_off_disables_stdio_logging() -> None:
    root = Path(__file__).resolve().parents[2]
    src_dir = str(root / "src")

    env = os.environ.copy()
    env["MCP_LOG_LEVEL"] = "OFF"
    env["MCP_LOGGING"] = "1"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_dir if not existing_pythonpath else f"{src_dir}{os.pathsep}{existing_pythonpath}"
    )

    code = (
        "import json, logging, warnings\n"
        "import relace_mcp.config.settings as settings\n"
        "import relace_mcp.server as server\n"
        "server._configure_logging_for_stdio()\n"
        "logging.getLogger('t').warning('should not appear')\n"
        "warnings.warn('should not appear')\n"
        "print(json.dumps({'mcp_log_level': settings.MCP_LOG_LEVEL, 'mcp_logging_enabled': settings.MCP_LOGGING_ENABLED}))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr.strip() == ""

    payload = json.loads(completed.stdout.strip())
    assert payload["mcp_log_level"] > logging.CRITICAL
    assert payload["mcp_logging_enabled"] is False
