import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import LSP_TIMEOUT_SECONDS, MAX_LSP_RESULTS
from .paths import map_repo_path

if TYPE_CHECKING:
    from relace_mcp.lsp import Location

logger = logging.getLogger(__name__)


@dataclass
class LSPQueryParams:
    """Parameters for find_symbol tool.

    Note: line and column are 0-indexed. view_file shows 1-indexed line numbers,
    so subtract 1 when using positions from view_file output.
    """

    action: str  # "definition" | "references"
    file: str
    line: int  # 0-indexed
    column: int  # 0-indexed


def lsp_query_handler(params: LSPQueryParams, base_dir: str) -> str:
    """LSP query handler using basedpyright.

    Thread-safe through LSPClientManager's internal locking.
    First call incurs startup delay, subsequent calls are fast.
    """
    # Validate action first (no need for imports)
    if params.action not in ("definition", "references"):
        return f"Error: Unknown action '{params.action}'. Use 'definition' or 'references'."

    if not isinstance(params.line, int) or not isinstance(params.column, int):
        return "Error: line and column must be integers (0-indexed)."

    if params.line < 0:
        return "Error: line must be >= 0 (0-indexed)."

    if params.column < 0:
        return "Error: column must be >= 0 (0-indexed)."

    # Path validation and mapping
    try:
        fs_path = map_repo_path(params.file, base_dir)
        abs_path = Path(fs_path).resolve()
        resolved_base_dir = str(Path(base_dir).resolve())

        if not abs_path.exists():
            return f"Error: File not found: {params.file}"
        if abs_path.suffix not in (".py", ".pyi"):
            return f"Error: find_symbol only supports Python files, got: {abs_path.suffix}"

        rel_path = str(abs_path.relative_to(resolved_base_dir))
    except ValueError as e:
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

        if params.action == "definition":
            results = client.definition(rel_path, params.line, params.column)
        else:
            results = client.references(rel_path, params.line, params.column)

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
