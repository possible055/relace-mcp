from pathlib import Path

from ..metrics.ranges import merge_ranges
from .treesitter import TREE_SITTER_AVAILABLE, get_parser

if TREE_SITTER_AVAILABLE:
    from tree_sitter import Tree


def _find_enclosing_node(
    tree: "Tree",
    line: int,
    *,
    node_types: frozenset[str] = frozenset({"function_definition", "class_definition"}),
) -> tuple[int, int] | None:
    """Find smallest enclosing node of given types for a line (1-indexed).

    Returns (start_line, end_line) 1-indexed, or None if not found.
    """
    target_row = line - 1  # tree-sitter uses 0-indexed rows
    cursor = tree.walk()

    best_match: tuple[int, int] | None = None
    best_size = float("inf")

    def visit() -> None:
        nonlocal best_match, best_size
        node = cursor.node
        start_row = node.start_point.row
        end_row = node.end_point.row

        if start_row <= target_row <= end_row:
            if node.type in node_types:
                size = end_row - start_row
                if size < best_size:
                    best_size = size
                    best_match = (start_row + 1, end_row + 1)

            if cursor.goto_first_child():
                while True:
                    visit()
                    if not cursor.goto_next_sibling():
                        break
                cursor.goto_parent()

    visit()
    return best_match


def normalize_to_ast_spans(
    file_path: Path,
    line_numbers: set[int],
    *,
    context_padding: int = 2,
) -> list[tuple[int, int]]:
    """Expand line numbers to enclosing AST node boundaries.

    For each line number, finds the smallest enclosing function or class
    definition and expands the range to cover the entire node.

    Args:
        file_path: Path to Python source file
        line_numbers: Set of 1-indexed line numbers to normalize
        context_padding: Extra lines above/below each span (default: 2)

    Returns:
        List of (start_line, end_line) tuples covering complete AST nodes.
        Falls back to original ranges if parsing fails.
    """
    if not line_numbers:
        return []

    try:
        content = file_path.read_bytes()
    except OSError:
        return _lines_to_ranges_fallback(line_numbers, context_padding)

    parser = get_parser()
    tree = parser.parse(content)

    if tree.root_node.has_error:
        return _lines_to_ranges_fallback(line_numbers, context_padding)

    spans: list[tuple[int, int]] = []
    unmatched_lines: set[int] = set()

    for line in sorted(line_numbers):
        if line < 1:
            continue
        node_span = _find_enclosing_node(tree, line)
        if node_span:
            spans.append(node_span)
        else:
            unmatched_lines.add(line)

    for line in unmatched_lines:
        start = max(1, line - context_padding)
        end = line + context_padding
        spans.append((start, end))

    merged = merge_ranges(spans)

    if context_padding > 0:
        padded: list[tuple[int, int]] = []
        for start, end in merged:
            padded.append((max(1, start - context_padding), end + context_padding))
        merged = merge_ranges(padded)

    return merged


def _lines_to_ranges_fallback(lines: set[int], context_padding: int) -> list[tuple[int, int]]:
    if not lines:
        return []
    sorted_lines = sorted(line for line in lines if line > 0)
    if not sorted_lines:
        return []

    ranges: list[tuple[int, int]] = []
    start = prev = sorted_lines[0]

    for line in sorted_lines[1:]:
        if line <= prev + 1 + (context_padding * 2):
            prev = line
        else:
            ranges.append((max(1, start - context_padding), prev + context_padding))
            start = prev = line

    ranges.append((max(1, start - context_padding), prev + context_padding))
    return merge_ranges(ranges)
