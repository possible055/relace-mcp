from pathlib import Path

import pytest

from relace_dashboard.log_reader import get_log_path


class TestDashboardLogPath:
    def test_mcp_log_path_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOG_PATH", "/tmp/custom.log")
        monkeypatch.delenv("MCP_LOG_DIR", raising=False)
        assert get_log_path() == Path("/tmp/custom.log")

    def test_mcp_log_dir_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_LOG_PATH", raising=False)
        monkeypatch.setenv("MCP_LOG_DIR", "/tmp/logdir")
        assert get_log_path() == Path("/tmp/logdir/relace.log")

    def test_default_platformdirs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_LOG_PATH", raising=False)
        monkeypatch.delenv("MCP_LOG_DIR", raising=False)
        result = get_log_path()
        assert result.name == "relace.log"

    def test_mcp_log_path_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_LOG_PATH", "/tmp/priority.log")
        monkeypatch.setenv("MCP_LOG_DIR", "/tmp/other")
        assert get_log_path() == Path("/tmp/priority.log")
