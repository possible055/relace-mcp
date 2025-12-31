import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from relace_mcp.utils import map_path_no_resolve

from .constants import LSP_TIMEOUT_SECONDS, MAX_LSP_RESULTS

if TYPE_CHECKING:
    from relace_mcp.lsp import Location

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

    # Path validation and mapping
    try:
        fs_path = map_path_no_resolve(params.file, base_dir)
        if fs_path.is_symlink():
            return f"Error: Symlinks not allowed: {params.file}"
        abs_path = fs_path.resolve()
        resolved_base_dir = str(Path(base_dir).resolve())

        # Validate path is within base_dir FIRST to prevent information disclosure
        try:
            rel_path = str(abs_path.relative_to(resolved_base_dir))
        except ValueError:
            return f"Error: Invalid path: {params.file}"

        if not abs_path.exists():
            return f"Error: File not found: {params.file}"
        if abs_path.suffix not in (".py", ".pyi"):
            return f"Error: find_symbol only supports Python files, got: {abs_path.suffix}"
    except (OSError, RuntimeError, ValueError) as e:
        return f"Error: Invalid path: {e}"

    # Lazy import to avoid loading lsp module if not used
    try:
        from relace_mcp.lsp import PYTHON_CONFIG, LSPClientManager, LSPError
    except ImportError as e:
        return f"Error: LSP dependencies not available: {e}. Run: pip install basedpyright"

    # Execute LSP request through manager
    try:
        manager = LSPClientManager.get_instance()
        client = manager.get_client(
            PYTHON_CONFIG, resolved_base_dir, timeout_seconds=LSP_TIMEOUT_SECONDS
        )

        def do_query(line: int, column: int) -> "list[Location]":
            if params.action == "definition":
                return client.definition(rel_path, line, column)
            return client.references(rel_path, line, column)

        # Try the requested position first
        results = do_query(line_0, column_0)

        # Fallback: if no results, try finding symbols on the line
        # This handles cases where column points to keywords (def, class) instead of symbol names
        if not results:
            try:
                with open(abs_path, encoding="utf-8", errors="replace") as f:
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

    except LSPError as e:
        if "not found" in str(e).lower():
            return "Error: basedpyright-langserver not found. Run: pip install basedpyright"
        return f"Error: {e}"
    except Exception as exc:
        logger.warning("LSP query failed: %s", exc)
        return f"Error: LSP query failed: {exc}"


def _format_lsp_results(results: "list[Location]", base_dir: str) -> str:
    """Format LSP results into grep-like output."""
    if not results:
        return "No results found."

    lines = []
    for r in results[:MAX_LSP_RESULTS]:
        line_str = r.to_grep_format(base_dir)
        lines.append(line_str)

    if len(results) > MAX_LSP_RESULTS:
        lines.append(f"... capped at {MAX_LSP_RESULTS} results (total: {len(results)})")

    return "\n".join(lines)
