import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from relace_mcp.tools.search._impl.lsp import (
    LSPQueryParams,
    _format_lsp_results,
    lsp_query_handler,
)


class TestLSPQueryParams:
    """Tests for LSPQueryParams dataclass."""

    def test_create_params(self) -> None:
        params = LSPQueryParams(
            action="definition",
            file="/repo/main.py",
            line=10,
            column=5,
        )
        assert params.action == "definition"
        assert params.file == "/repo/main.py"
        assert params.line == 10
        assert params.column == 5


class TestFormatLSPResults:
    """Tests for _format_lsp_results helper function."""

    def test_empty_results(self) -> None:
        result = _format_lsp_results([], "/base")
        assert result == "No results found."

    def test_location_format(self) -> None:
        # Import Location from the lsp module
        from relace_mcp.lsp import Location

        results = [Location(uri="file:///base/src/main.py", line=10, character=4)]
        result = _format_lsp_results(results, "/base")
        assert "/repo/src/main.py:11:5" in result

    def test_multiple_results(self) -> None:
        from relace_mcp.lsp import Location

        results = [
            Location(uri="file:///base/a.py", line=1, character=0),
            Location(uri="file:///base/b.py", line=2, character=5),
        ]
        result = _format_lsp_results(results, "/base")
        lines = result.split("\n")
        assert len(lines) == 2
        assert "/repo/a.py:2:1" in lines[0]
        assert "/repo/b.py:3:6" in lines[1]

    def test_result_capping(self) -> None:
        from relace_mcp.lsp import Location

        results = [
            Location(uri=f"file:///base/file{i}.py", line=i, character=0) for i in range(100)
        ]
        result = _format_lsp_results(results, "/base")
        assert "capped at 50 results" in result
        # Note: simplified message no longer includes total count

    def test_directory_boundary_matching(self) -> None:
        """Test: paths outside base_dir are filtered out.

        e.g., /home/user/project should NOT match /home/user/project123
        and such external paths should be filtered.
        """
        from relace_mcp.lsp import Location

        results = [Location(uri="file:///home/user/project123/file.py", line=0, character=0)]
        result = _format_lsp_results(results, "/home/user/project")
        # External paths are filtered out
        assert result == "No results found (all results are outside repository)."

    def test_base_dir_with_trailing_slash(self) -> None:
        """base_dir with trailing slash should work correctly."""
        from relace_mcp.lsp import Location

        results = [Location(uri="file:///base/src/main.py", line=5, character=10)]
        result = _format_lsp_results(results, "/base/")
        assert "/repo/src/main.py:6:11" in result


class TestLSPQueryHandler:
    """Tests for lsp_query_handler function."""

    def test_invalid_action_returns_error(self, tmp_path: Path) -> None:
        params = LSPQueryParams(action="invalid", file="/repo/x.py", line=1, column=1)
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "Unknown action" in result

    def test_file_not_found_returns_error(self, tmp_path: Path) -> None:
        params = LSPQueryParams(
            action="definition",
            file="/repo/nonexistent.py",
            line=1,
            column=1,
        )
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "not found" in result

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_js_file_uses_typescript_config(
        self, mock_manager_cls: MagicMock, tmp_path: Path
    ) -> None:
        from relace_mcp.lsp import Location

        js_file = tmp_path / "test.js"
        js_file.write_text("const x = 1;")

        mock_client = MagicMock()
        mock_client.definition.return_value = [Location(uri=js_file.as_uri(), line=0, character=0)]
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_client
        mock_session.__exit__.return_value = False
        mock_manager = MagicMock()
        mock_manager.session.return_value = mock_session
        mock_manager_cls.get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="definition",
            file="/repo/test.js",
            line=1,
            column=1,
        )
        result = lsp_query_handler(params, str(tmp_path))

        called_config = mock_manager.session.call_args[0][0]
        assert called_config.language_id == "typescript"
        mock_client.definition.assert_called_once()
        assert "Error" not in result
        assert "test.js:1:1" in result

    def test_negative_line_returns_error(self, tmp_path: Path) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")
        params = LSPQueryParams(
            action="definition",
            file="/repo/test.py",
            line=-1,
            column=1,
        )
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "line" in result

    def test_negative_column_returns_error(self, tmp_path: Path) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")
        params = LSPQueryParams(
            action="definition",
            file="/repo/test.py",
            line=1,
            column=-1,
        )
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "column" in result

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_symlinked_base_dir_works(self, mock_manager_cls: MagicMock, tmp_path: Path) -> None:
        """Regression test: symlinked base_dir should not cause ValueError.

        When base_dir is a symlink, Path.resolve() on the file returns the
        real path, but relative_to with the unresolved base_dir fails.
        """
        from relace_mcp.lsp import Location

        # Create actual directory with a Python file
        actual_dir = tmp_path / "actual"
        actual_dir.mkdir()
        py_file = actual_dir / "test.py"
        py_file.write_text("x = 1\n")

        # Create symlink to actual directory
        symlink_dir = tmp_path / "symlink"
        try:
            symlink_dir.symlink_to(actual_dir)
        except (OSError, NotImplementedError) as e:
            import pytest

            pytest.skip(f"symlink is not supported in this environment: {e!r}")

        mock_client = MagicMock()
        mock_client.definition.return_value = [
            Location(uri=(actual_dir / "test.py").as_uri(), line=0, character=0)
        ]
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_client
        mock_session.__exit__.return_value = False
        mock_manager = MagicMock()
        mock_manager.session.return_value = mock_session
        mock_manager_cls.get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="definition",
            file="/repo/test.py",
            line=1,
            column=1,
        )
        # Pass symlink path as base_dir - this should NOT raise ValueError
        result = lsp_query_handler(params, str(symlink_dir))

        # Should succeed, not return "Invalid path" error
        assert "Error" not in result
        mock_client.definition.assert_called_once()

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_definition_calls_manager(self, mock_manager_cls: MagicMock, tmp_path: Path) -> None:
        from relace_mcp.lsp import Location

        # Create a Python file
        py_file = tmp_path / "test.py"
        py_file.write_text("def hello():\n    pass\n")

        mock_client = MagicMock()
        mock_client.definition.return_value = [
            Location(uri=(tmp_path / "test.py").as_uri(), line=0, character=4)
        ]
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_client
        mock_session.__exit__.return_value = False
        mock_manager = MagicMock()
        mock_manager.session.return_value = mock_session
        mock_manager_cls.get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="definition",
            file="/repo/test.py",
            line=1,
            column=5,
        )
        result = lsp_query_handler(params, str(tmp_path))

        mock_client.definition.assert_called_once()
        assert "test.py:1:5" in result

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_timeout_returns_error(self, mock_manager_cls: MagicMock, tmp_path: Path) -> None:
        from relace_mcp.lsp import LSPError

        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")

        mock_client = MagicMock()
        mock_client.definition.side_effect = LSPError("Request textDocument/definition timed out")
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_client
        mock_session.__exit__.return_value = False
        mock_manager = MagicMock()
        mock_manager.session.return_value = mock_session
        mock_manager_cls.get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="definition",
            file="/repo/test.py",
            line=1,
            column=1,
        )
        result = lsp_query_handler(params, str(tmp_path))

        assert "Error" in result
        assert "timed out" in result

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_references_calls_manager(self, mock_manager_cls: MagicMock, tmp_path: Path) -> None:
        from relace_mcp.lsp import Location

        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\nprint(x)\n")

        mock_client = MagicMock()
        mock_client.references.return_value = [
            Location(uri=(tmp_path / "test.py").as_uri(), line=0, character=0),
            Location(uri=(tmp_path / "test.py").as_uri(), line=1, character=6),
        ]
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_client
        mock_session.__exit__.return_value = False
        mock_manager = MagicMock()
        mock_manager.session.return_value = mock_session
        mock_manager_cls.get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="references",
            file="/repo/test.py",
            line=1,
            column=1,
        )
        result = lsp_query_handler(params, str(tmp_path))

        mock_client.references.assert_called_once()
        lines = result.split("\n")
        assert len(lines) == 2


class TestLSPClientManager:
    """Tests for LSPClientManager singleton."""

    def test_singleton_instance(self) -> None:
        from relace_mcp.lsp import LSPClientManager

        # Reset singleton for test isolation
        LSPClientManager._instance = None

        m1 = LSPClientManager.get_instance()
        m2 = LSPClientManager.get_instance()
        assert m1 is m2

        # Cleanup
        LSPClientManager._instance = None

    def test_singleton_thread_safety(self) -> None:
        from relace_mcp.lsp import LSPClientManager

        LSPClientManager._instance = None

        instances: list = []
        errors: list[Exception] = []

        def get_manager() -> None:
            try:
                instances.append(LSPClientManager.get_instance())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_manager) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(instances) == 10
        # All should be the same instance
        assert all(inst is instances[0] for inst in instances)

        # Cleanup
        LSPClientManager._instance = None

    def test_manager_initial_state(self) -> None:
        from relace_mcp.lsp import LSPClientManager

        LSPClientManager._instance = None

        manager = LSPClientManager.get_instance()
        assert len(manager._clients) == 0

        # Cleanup
        LSPClientManager._instance = None

    @patch("relace_mcp.lsp.client.LSPClient")
    def test_manager_lru_eviction(self, mock_client_cls: MagicMock, monkeypatch) -> None:
        from relace_mcp.lsp import PYTHON_CONFIG, LSPClientManager

        monkeypatch.setenv("SEARCH_LSP_MAX_CLIENTS", "2")
        LSPClientManager._instance = None

        c1 = MagicMock()
        c2 = MagicMock()
        c3 = MagicMock()
        mock_client_cls.side_effect = [c1, c2, c3]

        manager = LSPClientManager.get_instance()
        manager.get_client(PYTHON_CONFIG, "/w1")
        manager.get_client(PYTHON_CONFIG, "/w2")
        # Refresh /w1 so /w2 becomes LRU.
        manager.get_client(PYTHON_CONFIG, "/w1")
        manager.get_client(PYTHON_CONFIG, "/w3")

        c2.shutdown.assert_called_once()
        c1.shutdown.assert_not_called()
        c3.shutdown.assert_not_called()

        # Cleanup
        LSPClientManager._instance = None

    @patch("relace_mcp.lsp.client.LSPClient")
    def test_manager_soft_cap_does_not_evict_leased(
        self, mock_client_cls: MagicMock, monkeypatch
    ) -> None:
        from relace_mcp.lsp import PYTHON_CONFIG, LSPClientManager

        monkeypatch.setenv("SEARCH_LSP_MAX_CLIENTS", "1")
        LSPClientManager._instance = None

        c1 = MagicMock()
        c2 = MagicMock()
        mock_client_cls.side_effect = [c1, c2]

        manager = LSPClientManager.get_instance()

        with manager.session(PYTHON_CONFIG, "/w1"):
            manager.get_client(PYTHON_CONFIG, "/w2")
            assert ("/w1", "python") in manager._clients
            assert ("/w2", "python") in manager._clients
            c1.shutdown.assert_not_called()
            c2.shutdown.assert_not_called()
            assert len(manager._clients) == 2

        assert len(manager._clients) == 1
        assert ("/w2", "python") in manager._clients
        c1.shutdown.assert_called_once()
        c2.shutdown.assert_not_called()

        # Cleanup
        LSPClientManager._instance = None


class TestLSPClientSync:
    def test_sync_runs_before_open_file(self, tmp_path: Path) -> None:
        """Ensures workspace sync cannot restart the server after didOpen."""
        from relace_mcp.lsp import PYTHON_CONFIG
        from relace_mcp.lsp.client import LSPClient

        client = LSPClient(PYTHON_CONFIG, str(tmp_path))
        client._initialized = True

        calls: list[str] = []

        def fake_sync() -> None:
            calls.append("sync")

        def fake_open_file(file_path: str) -> str:
            calls.append("open")
            return "file:///tmp/test.py"

        def fake_close_file(uri: str) -> None:
            calls.append("close")

        def fake_send_request(method: str, params: dict, **kwargs):
            calls.append(f"request:{method}")
            return []

        client._sync_workspace_changes_best_effort = fake_sync  # type: ignore[assignment]
        client._open_file = fake_open_file  # type: ignore[assignment]
        client._close_file = fake_close_file  # type: ignore[assignment]
        client._send_request = fake_send_request  # type: ignore[assignment]

        client.definition("test.py", 0, 0)
        assert calls[:2] == ["sync", "open"]

    def test_sync_does_not_skip_workspace_root_named_build(self, tmp_path: Path) -> None:
        from relace_mcp.lsp import PYTHON_CONFIG
        from relace_mcp.lsp.client import LSPClient

        workspace_root = tmp_path / "build"
        workspace_root.mkdir()
        (workspace_root / "main.py").write_text("x = 1\n")

        client = LSPClient(PYTHON_CONFIG, str(workspace_root))
        client._initialized = True
        client._fs_last_sync = -1_000_000.0

        client._sync_workspace_changes()
        assert "main.py" in client._fs_snapshot
