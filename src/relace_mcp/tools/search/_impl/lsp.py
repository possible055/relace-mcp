import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from relace_mcp.utils import map_path_no_resolve

from .constants import LSP_TIMEOUT_SECONDS, MAX_LSP_RESULTS

if TYPE_CHECKING:
    from relace_mcp.lsp import Location, LSPClient

logger = logging.getLogger(__name__)

# Pattern to find Python identifiers (for column fallback)
_IDENTIFIER_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
# Keywords to skip when searching for symbols
_PYTHON_KEYWORDS = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
    }
)


# ---------------------------------------------------------------------------
# Internal Helpers (reduces ~200 lines of duplication across 5 handlers)
# ---------------------------------------------------------------------------


@dataclass
class _ValidatedPath:
    """Result of path validation for LSP handlers."""

    rel_path: str  # Relative path for LSP client
    abs_path: Path  # Absolute path for file operations
    resolved_base_dir: str  # Resolved base directory


def _validate_python_path(file: str, base_dir: str) -> _ValidatedPath | str:
    """Validate and resolve a Python file path for LSP operations.

    Args:
        file: Input file path (may be /repo/... format).
        base_dir: Base directory for path resolution.

    Returns:
        _ValidatedPath on success, or error message string on failure.
    """
    try:
        fs_path = map_path_no_resolve(file, base_dir)
        if fs_path.is_symlink():
            return f"Error: Symlinks not allowed: {file}"
        abs_path = fs_path.resolve()
        resolved_base_dir = str(Path(base_dir).resolve())

        try:
            rel_path = str(abs_path.relative_to(resolved_base_dir))
        except ValueError:
            return f"Error: Invalid path: {file}"

        if not abs_path.exists():
            return f"Error: File not found: {file}"
        if abs_path.suffix not in (".py", ".pyi"):
            return f"Error: Only Python files supported, got: {abs_path.suffix}"

        return _ValidatedPath(rel_path, abs_path, resolved_base_dir)
    except (OSError, RuntimeError, ValueError) as e:
        return f"Error: Invalid path: {e}"


def _get_lsp_client(base_dir: str) -> "tuple[LSPClient, str, type] | str":
    """Get LSP client with lazy import.

    Args:
        base_dir: Base directory for the LSP workspace.

    Returns:
        Tuple of (client, resolved_base_dir, LSPError_class) on success,
        or error message string on failure.
    """
    try:
        from relace_mcp.lsp import PYTHON_CONFIG, LSPClientManager, LSPError
    except ImportError as e:
        return f"Error: LSP dependencies not available: {e}. Run: pip install basedpyright"

    resolved_base_dir = str(Path(base_dir).resolve())
    manager = LSPClientManager.get_instance()
    client = manager.get_client(
        PYTHON_CONFIG, resolved_base_dir, timeout_seconds=LSP_TIMEOUT_SECONDS
    )
    return (client, resolved_base_dir, LSPError)


def _handle_lsp_error(exc: Exception, operation: str) -> str:
    """Format LSP error into user-friendly message.

    Args:
        exc: The exception that occurred.
        operation: Description of the operation that failed.

    Returns:
        Formatted error message.
    """
    # Import LSPError for isinstance check
    try:
        from relace_mcp.lsp import LSPError

        if isinstance(exc, LSPError):
            if "not found" in str(exc).lower():
                return "Error: basedpyright-langserver not found. Run: pip install basedpyright"
            return f"Error: {exc}"
    except ImportError:
        pass

    logger.warning("LSP %s failed: %s", operation, exc)
    return f"Error: LSP {operation} failed: {exc}"


@dataclass
class LSPQueryParams:
    """Parameters for find_symbol tool.

    Note: line and column are 1-indexed to match view_file output.
    Internally converted to 0-indexed for LSP protocol.
    """

    action: str  # "definition" | "references"
    file: str
    line: int  # 1-indexed
    column: int  # 1-indexed


@dataclass
class SearchSymbolParams:
    """Parameters for search_symbol tool."""

    query: str


@dataclass
class ListSymbolsParams:
    """Parameters for list_symbols tool."""

    file: str


@dataclass
class GetTypeParams:
    """Parameters for get_type tool."""

    file: str
    line: int  # 1-indexed
    column: int  # 1-indexed


@dataclass
class CallGraphParams:
    """Parameters for call_graph tool."""

    file: str
    line: int  # 1-indexed
    column: int  # 1-indexed
    direction: str  # "incoming" | "outgoing"


def _find_symbol_columns(line_content: str) -> list[int]:
    """Find column positions of potential symbols in a line (skipping keywords)."""
    columns = []
    for match in _IDENTIFIER_PATTERN.finditer(line_content):
        identifier = match.group(1)
        if identifier not in _PYTHON_KEYWORDS:
            columns.append(match.start())
    return columns


def lsp_query_handler(params: LSPQueryParams, base_dir: str) -> str:
    """LSP query handler using basedpyright.

    Thread-safe through LSPClientManager's internal locking.
    First call incurs startup delay, subsequent calls are fast.

    Args:
        params: Query parameters with 1-indexed line/column (matching view_file output).
        base_dir: Base directory for resolving paths.

    Column fallback: If initial column yields no results, automatically tries
    other symbol positions on the same line.
    """
    # Validate action first (no need for imports)
    if params.action not in ("definition", "references"):
        return f"Error: Unknown action '{params.action}'. Use 'definition' or 'references'."

    if not isinstance(params.line, int) or not isinstance(params.column, int):
        return "Error: line and column must be integers (1-indexed)."

    if params.line < 1:
        return "Error: line must be >= 1 (1-indexed)."

    if params.column < 1:
        return "Error: column must be >= 1 (1-indexed)."

    # Convert to 0-indexed for LSP protocol
    line_0 = params.line - 1
    column_0 = params.column - 1

    path_result = _validate_python_path(params.file, base_dir)
    if isinstance(path_result, str):
        return path_result

    client_result = _get_lsp_client(base_dir)
    if isinstance(client_result, str):
        return client_result
    client, resolved_base_dir, _ = client_result

    try:

        def do_query(line: int, column: int) -> "list[Location]":
            if params.action == "definition":
                return client.definition(path_result.rel_path, line, column)
            return client.references(path_result.rel_path, line, column)

        # Try the requested position first
        results = do_query(line_0, column_0)

        # Fallback: if no results, try finding symbols on the line
        # This handles cases where column points to keywords (def, class) instead of symbol names
        if not results:
            try:
                with open(path_result.abs_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    if 0 <= line_0 < len(lines):
                        line_content = lines[line_0]
                        symbol_columns = _find_symbol_columns(line_content)
                        # Skip the originally requested column
                        for col in symbol_columns:
                            if col == column_0:
                                continue
                            results = do_query(line_0, col)
                            if results:
                                logger.debug(
                                    "Column fallback succeeded: line=%d, col=%d -> %d",
                                    line_0,
                                    column_0,
                                    col,
                                )
                                break
            except Exception as e:
                logger.debug("Column fallback failed: %s", e)

        return _format_lsp_results(results, resolved_base_dir)

    except Exception as exc:
        return _handle_lsp_error(exc, "query")


def _format_lsp_results(results: "list[Location]", base_dir: str) -> str:
    """Format LSP results into grep-like output, filtering external paths.

    Filter-first-then-cap: filters external paths before applying result limit
    to ensure repo-internal results aren't excluded.
    """
    if not results:
        return "No results found."

    lines = []
    for r in results:
        line_str = r.to_grep_format(base_dir)
        if line_str is not None:
            lines.append(line_str)
            if len(lines) >= MAX_LSP_RESULTS:
                break

    if not lines:
        return "No results found (all results are outside repository)."

    if len(lines) >= MAX_LSP_RESULTS:
        lines.append(f"... capped at {MAX_LSP_RESULTS} results")

    return "\n".join(lines)


def search_symbol_handler(params: SearchSymbolParams, base_dir: str) -> str:
    """Search for symbols by name across the workspace using LSP.

    Thread-safe through LSPClientManager's internal locking.
    First call incurs startup delay, subsequent calls are fast.
    """
    if not params.query or not params.query.strip():
        return "Error: query cannot be empty."

    query = params.query.strip()

    client_result = _get_lsp_client(base_dir)
    if isinstance(client_result, str):
        return client_result
    client, resolved_base_dir, _ = client_result

    try:
        results = client.workspace_symbols(query)

        if not results:
            return "No symbols found."

        lines = []
        for r in results:
            formatted = r.to_grep_format(resolved_base_dir)
            if formatted is not None:
                lines.append(formatted)
                if len(lines) >= MAX_LSP_RESULTS:
                    break

        if not lines:
            return "No symbols found (all results are outside repository)."

        if len(lines) >= MAX_LSP_RESULTS:
            lines.append(f"... capped at {MAX_LSP_RESULTS} results")

        return "\n".join(lines)

    except Exception as exc:
        return _handle_lsp_error(exc, "symbol search")


def list_symbols_handler(params: ListSymbolsParams, base_dir: str) -> str:
    """List all symbols defined in a file using LSP.

    Thread-safe through LSPClientManager's internal locking.
    First call incurs startup delay, subsequent calls are fast.
    """
    if not params.file or not params.file.strip():
        return "Error: file path cannot be empty."

    path_result = _validate_python_path(params.file, base_dir)
    if isinstance(path_result, str):
        return path_result

    client_result = _get_lsp_client(base_dir)
    if isinstance(client_result, str):
        return client_result
    client, _, _ = client_result

    try:
        results = client.document_symbols(path_result.rel_path)

        if not results:
            return "No symbols found in file."

        lines = []
        for sym in results:
            lines.append(sym.to_outline_str())

        return "\n".join(lines)

    except Exception as exc:
        return _handle_lsp_error(exc, "document symbols")


def get_type_handler(params: GetTypeParams, base_dir: str) -> str:
    """Get type information at a position using LSP hover.

    Thread-safe through LSPClientManager's internal locking.
    First call incurs startup delay, subsequent calls are fast.
    """
    if not isinstance(params.line, int) or not isinstance(params.column, int):
        return "Error: line and column must be integers (1-indexed)."
    if params.line < 1:
        return "Error: line must be >= 1 (1-indexed)."
    if params.column < 1:
        return "Error: column must be >= 1 (1-indexed)."

    # Convert to 0-indexed for LSP protocol
    line_0 = params.line - 1
    column_0 = params.column - 1

    path_result = _validate_python_path(params.file, base_dir)
    if isinstance(path_result, str):
        return path_result

    client_result = _get_lsp_client(base_dir)
    if isinstance(client_result, str):
        return client_result
    client, _, _ = client_result

    try:
        result = client.hover(path_result.rel_path, line_0, column_0)

        if not result:
            return "No type information available."

        return result.to_display_str()

    except Exception as exc:
        return _handle_lsp_error(exc, "hover")


def call_graph_handler(params: CallGraphParams, base_dir: str) -> str:
    """Get call hierarchy (who calls / what is called) using LSP.

    Thread-safe through LSPClientManager's internal locking.
    First call incurs startup delay, subsequent calls are fast.
    """
    if params.direction not in ("incoming", "outgoing"):
        return "Error: direction must be 'incoming' or 'outgoing'."

    if not isinstance(params.line, int) or not isinstance(params.column, int):
        return "Error: line and column must be integers (1-indexed)."
    if params.line < 1:
        return "Error: line must be >= 1 (1-indexed)."
    if params.column < 1:
        return "Error: column must be >= 1 (1-indexed)."

    if not params.file or not params.file.strip():
        return "Error: file path cannot be empty."

    line_0 = params.line - 1
    column_0 = params.column - 1

    path_result = _validate_python_path(params.file, base_dir)
    if isinstance(path_result, str):
        return path_result

    client_result = _get_lsp_client(base_dir)
    if isinstance(client_result, str):
        return client_result
    client, resolved_base_dir, _ = client_result

    try:
        results = client.call_hierarchy(path_result.rel_path, line_0, column_0, params.direction)

        if not results:
            direction_desc = "callers" if params.direction == "incoming" else "callees"
            return f"No {direction_desc} found. Ensure cursor is on a function/method name."

        lines = []
        header = "Called by:" if params.direction == "incoming" else "Calls:"
        lines.append(header)
        result_count = 0
        for r in results:
            display_str = r.to_display_str(resolved_base_dir)
            if display_str is not None:
                lines.append("  " + display_str)
                result_count += 1
                if result_count >= MAX_LSP_RESULTS:
                    break

        if len(lines) == 1:  # Only header, no results after filtering
            direction_desc = "callers" if params.direction == "incoming" else "callees"
            return f"No {direction_desc} found within repository."

        if result_count >= MAX_LSP_RESULTS:
            lines.append(f"  ... capped at {MAX_LSP_RESULTS} results")

        return "\n".join(lines)

    except Exception as exc:
        return _handle_lsp_error(exc, "call hierarchy")
