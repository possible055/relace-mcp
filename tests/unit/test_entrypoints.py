import runpy
import sys
import types
from unittest.mock import MagicMock


def test_python_m_entrypoint_calls_server_main(monkeypatch) -> None:
    import relace_mcp.server as server_mod

    called = {"count": 0}

    def _fake_main() -> None:
        called["count"] += 1

    monkeypatch.setattr(server_mod, "main", _fake_main)

    runpy.run_module("relace_mcp", run_name="__main__")
    assert called["count"] == 1


def test_dashboard_entrypoint_calls_app_main(monkeypatch) -> None:
    import relace_mcp.dashboard as dashboard_mod

    monkeypatch.delitem(sys.modules, "relace_mcp.dashboard.app", raising=False)

    fake_app = types.ModuleType("relace_mcp.dashboard.app")
    fake_app.main = MagicMock()
    monkeypatch.setitem(sys.modules, "relace_mcp.dashboard.app", fake_app)

    dashboard_mod.main()

    fake_app.main.assert_called_once()
