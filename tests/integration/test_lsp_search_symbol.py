from unittest.mock import MagicMock, patch

from relace_mcp.lsp.types import SymbolInfo
from relace_mcp.tools.search._impl.lsp import SearchSymbolParams, search_symbol_handler


class TestSymbolInfo:
    """Tests for SymbolInfo dataclass."""

    def test_kind_name_known(self) -> None:
        info = SymbolInfo(name="MyClass", kind=5, uri="file:///test.py", line=10, character=0)
        assert info.kind_name == "class"

    def test_kind_name_unknown(self) -> None:
        info = SymbolInfo(name="X", kind=999, uri="file:///test.py", line=0, character=0)
        assert info.kind_name == "unknown"

    def test_to_grep_format_basic(self) -> None:
        info = SymbolInfo(
            name="my_func", kind=12, uri="file:///base/src/main.py", line=5, character=4
        )
        result = info.to_grep_format("/base")
        assert "[function]" in result
        assert "/repo/src/main.py:6:5" in result
        assert "my_func" in result

    def test_to_grep_format_with_container(self) -> None:
        info = SymbolInfo(
            name="method",
            kind=6,
            uri="file:///base/test.py",
            line=10,
            character=8,
            container_name="MyClass",
        )
        result = info.to_grep_format("/base")
        assert "(MyClass)" in result


class TestSearchSymbolParams:
    """Tests for SearchSymbolParams dataclass."""

    def test_create_params(self) -> None:
        params = SearchSymbolParams(query="test_query")
        assert params.query == "test_query"


class TestSearchSymbolHandler:
    """Tests for search_symbol_handler function."""

    def test_empty_query_returns_error(self) -> None:
        params = SearchSymbolParams(query="")
        result = search_symbol_handler(params, "/tmp")
        assert "Error" in result
        assert "empty" in result

    def test_whitespace_query_returns_error(self) -> None:
        params = SearchSymbolParams(query="   ")
        result = search_symbol_handler(params, "/tmp")
        assert "Error" in result

    def test_short_query_returns_error(self) -> None:
        params = SearchSymbolParams(query="x")
        result = search_symbol_handler(params, "/tmp")
        assert "Error" in result
        assert "too short" in result

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_basic_search(self, mock_manager_cls: MagicMock, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.workspace_symbols.return_value = [
            SymbolInfo(
                name="TestClass",
                kind=5,
                uri=f"file://{tmp_path}/test.py",
                line=10,
                character=6,
            )
        ]
        mock_manager = MagicMock()
        mock_manager.get_client.return_value = mock_client
        mock_manager_cls.get_instance.return_value = mock_manager

        params = SearchSymbolParams(query="TestClass")
        result = search_symbol_handler(params, str(tmp_path))

        mock_client.workspace_symbols.assert_called_once_with("TestClass")
        assert "[class]" in result
        assert "TestClass" in result

    @patch("relace_mcp.lsp.LSPClientManager")
    def test_no_results(self, mock_manager_cls: MagicMock, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.workspace_symbols.return_value = []
        mock_manager = MagicMock()
        mock_manager.get_client.return_value = mock_client
        mock_manager_cls.get_instance.return_value = mock_manager

        params = SearchSymbolParams(query="NonExistent")
        result = search_symbol_handler(params, str(tmp_path))

        assert "No symbols found" in result
