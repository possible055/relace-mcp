import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from relace_mcp.tools.search.handlers.lsp import (
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
        assert "total: 100" in result

    def test_directory_boundary_matching(self) -> None:
        """Regression test: base_dir must match at directory boundary.

        e.g., /home/user/project should NOT match /home/user/project123
        """
        from relace_mcp.lsp import Location

        results = [Location(uri="file:///home/user/project123/file.py", line=0, character=0)]
        result = _format_lsp_results(results, "/home/user/project")
        # Should NOT be transformed to /repo/... since project123 != project
        assert result == "/home/user/project123/file.py:1:1"

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

    def test_non_python_file_returns_error(self, tmp_path: Path) -> None:
        js_file = tmp_path / "test.js"
        js_file.write_text("const x = 1;")
        params = LSPQueryParams(
            action="definition",
            file="/repo/test.js",
            line=1,
            column=1,
        )
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "Python files" in result

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
        symlink_dir.symlink_to(actual_dir)

        mock_client = MagicMock()
        mock_client.definition.return_value = [
            Location(uri=f"file://{actual_dir}/test.py", line=0, character=0)
        ]
        mock_manager = MagicMock()
        mock_manager.get_client.return_value = mock_client
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
            Location(uri=f"file://{tmp_path}/test.py", line=0, character=4)
        ]
        mock_manager = MagicMock()
        mock_manager.get_client.return_value = mock_client
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
        mock_manager = MagicMock()
        mock_manager.get_client.return_value = mock_client
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
            Location(uri=f"file://{tmp_path}/test.py", line=0, character=0),
            Location(uri=f"file://{tmp_path}/test.py", line=1, character=6),
        ]
        mock_manager = MagicMock()
        mock_manager.get_client.return_value = mock_client
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
