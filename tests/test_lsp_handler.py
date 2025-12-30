import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.tools.search.handlers.lsp import (
    LSPQueryParams,
    LSPServerManager,
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
        results: list[dict[str, Any]] = [
            {
                "uri": "file:///base/src/main.py",
                "range": {"start": {"line": 10, "character": 4}},
            }
        ]
        result = _format_lsp_results(results, "/base")
        assert "/repo/src/main.py:11:4" in result

    def test_location_link_format(self) -> None:
        results: list[dict[str, Any]] = [
            {
                "targetUri": "file:///base/lib/util.py",
                "targetRange": {"start": {"line": 0, "character": 0}},
            }
        ]
        result = _format_lsp_results(results, "/base")
        assert "/repo/lib/util.py:1:0" in result

    def test_multiple_results(self) -> None:
        results: list[dict[str, Any]] = [
            {
                "uri": "file:///base/a.py",
                "range": {"start": {"line": 1, "character": 0}},
            },
            {
                "uri": "file:///base/b.py",
                "range": {"start": {"line": 2, "character": 5}},
            },
        ]
        result = _format_lsp_results(results, "/base")
        lines = result.split("\n")
        assert len(lines) == 2
        assert "/repo/a.py:2:0" in lines[0]
        assert "/repo/b.py:3:5" in lines[1]

    def test_result_capping(self) -> None:
        results: list[dict[str, Any]] = [
            {
                "uri": f"file:///base/file{i}.py",
                "range": {"start": {"line": i, "character": 0}},
            }
            for i in range(100)
        ]
        result = _format_lsp_results(results, "/base")
        assert "capped at 50 results" in result
        assert "total: 100" in result


class TestLSPQueryHandler:
    """Tests for lsp_query_handler function."""

    def test_invalid_action_returns_error(self, tmp_path: Path) -> None:
        params = LSPQueryParams(action="invalid", file="/repo/x.py", line=0, column=0)
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "Unknown action" in result

    def test_file_not_found_returns_error(self, tmp_path: Path) -> None:
        params = LSPQueryParams(
            action="definition",
            file="/repo/nonexistent.py",
            line=0,
            column=0,
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
            line=0,
            column=0,
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
            column=0,
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
            line=0,
            column=-1,
        )
        result = lsp_query_handler(params, str(tmp_path))
        assert "Error" in result
        assert "column" in result

    @patch("relace_mcp.tools.search.handlers.lsp.LSPServerManager.get_instance")
    def test_definition_calls_manager(self, mock_get_instance: MagicMock, tmp_path: Path) -> None:
        # Create a Python file
        py_file = tmp_path / "test.py"
        py_file.write_text("def hello():\n    pass\n")

        mock_manager = MagicMock()
        mock_manager.request_definition.return_value = [
            {
                "uri": f"file://{tmp_path}/test.py",
                "range": {"start": {"line": 0, "character": 4}},
            }
        ]
        mock_get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="definition",
            file="/repo/test.py",
            line=0,
            column=4,
        )
        result = lsp_query_handler(params, str(tmp_path))

        mock_manager.request_definition.assert_called_once()
        assert "test.py:1:4" in result

    @patch("relace_mcp.tools.search.handlers.lsp.LSPServerManager.get_instance")
    def test_references_calls_manager(self, mock_get_instance: MagicMock, tmp_path: Path) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\nprint(x)\n")

        mock_manager = MagicMock()
        mock_manager.request_references.return_value = [
            {
                "uri": f"file://{tmp_path}/test.py",
                "range": {"start": {"line": 0, "character": 0}},
            },
            {
                "uri": f"file://{tmp_path}/test.py",
                "range": {"start": {"line": 1, "character": 6}},
            },
        ]
        mock_get_instance.return_value = mock_manager

        params = LSPQueryParams(
            action="references",
            file="/repo/test.py",
            line=0,
            column=0,
        )
        result = lsp_query_handler(params, str(tmp_path))

        mock_manager.request_references.assert_called_once()
        lines = result.split("\n")
        assert len(lines) == 2


class TestLSPServerManager:
    """Tests for LSPServerManager singleton."""

    def test_singleton_instance(self) -> None:
        # Reset singleton for test isolation
        LSPServerManager._instance = None

        m1 = LSPServerManager.get_instance()
        m2 = LSPServerManager.get_instance()
        assert m1 is m2

        # Cleanup
        LSPServerManager._instance = None

    def test_singleton_thread_safety(self) -> None:
        LSPServerManager._instance = None

        instances: list[LSPServerManager] = []
        errors: list[Exception] = []

        def get_manager() -> None:
            try:
                instances.append(LSPServerManager.get_instance())
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
        LSPServerManager._instance = None

    def test_manager_initial_state(self) -> None:
        LSPServerManager._instance = None

        manager = LSPServerManager.get_instance()
        assert manager._initialized is False
        assert manager._server is None
        assert manager._context is None
        assert manager._workspace is None

        # Cleanup
        LSPServerManager._instance = None

    def test_request_exception_triggers_cleanup(self) -> None:
        LSPServerManager._instance = None
        manager = LSPServerManager.get_instance()

        context = MagicMock()
        server = MagicMock()
        server.request_definition.side_effect = RuntimeError("boom")

        manager._initialized = True
        manager._context = context
        manager._server = server
        manager._workspace = "/tmp"
        manager._ensure_server = MagicMock()

        with pytest.raises(RuntimeError, match="boom"):
            manager.request_definition("/tmp", "a.py", 0, 0)

        context.__exit__.assert_called_once()
        assert manager._initialized is False
        assert manager._server is None
        assert manager._context is None

        # Cleanup
        LSPServerManager._instance = None
