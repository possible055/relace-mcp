from relace_mcp.lsp.client import LSPClient, LSPClientManager
from relace_mcp.lsp.languages import get_config_for_file
from relace_mcp.lsp.languages.go import GO_CONFIG
from relace_mcp.lsp.languages.python import PYTHON_CONFIG
from relace_mcp.lsp.languages.rust import RUST_CONFIG
from relace_mcp.lsp.languages.typescript import TYPESCRIPT_CONFIG


class TestGetConfigForFile:
    def test_matches_extensions(self) -> None:
        assert get_config_for_file("a.py").language_id == "python"
        assert get_config_for_file("a.ts").language_id == "typescript"
        assert get_config_for_file("a.go").language_id == "go"
        assert get_config_for_file("a.rs").language_id == "rust"
        assert get_config_for_file("a.txt") is None


class TestLSPClientManagerMultiLanguage:
    def test_separates_clients_by_language(self, monkeypatch) -> None:
        monkeypatch.setattr(LSPClient, "start", lambda self: None)

        manager = LSPClientManager()
        manager._max_clients = 0
        workspace = "/tmp/relace-lsp-test"

        py_client = manager.get_client(PYTHON_CONFIG, workspace)
        ts_client = manager.get_client(TYPESCRIPT_CONFIG, workspace)
        go_client = manager.get_client(GO_CONFIG, workspace)
        rust_client = manager.get_client(RUST_CONFIG, workspace)

        assert py_client is manager.get_client(PYTHON_CONFIG, workspace)
        assert ts_client is manager.get_client(TYPESCRIPT_CONFIG, workspace)
        assert go_client is manager.get_client(GO_CONFIG, workspace)
        assert rust_client is manager.get_client(RUST_CONFIG, workspace)

        assert py_client is not ts_client
        assert py_client is not go_client
        assert py_client is not rust_client

        assert (workspace, "python") in manager._clients
        assert (workspace, "typescript") in manager._clients
        assert (workspace, "go") in manager._clients
        assert (workspace, "rust") in manager._clients

        manager._cleanup_all()
