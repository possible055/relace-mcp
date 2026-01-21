from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter import Tree

from .treesitter import extract_signature, get_parser


@dataclass
class FunctionScope:
    path: str
    function_name: str
    class_name: str | None
    start_line: int
    end_line: int
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "function": self.function_name,
            "class": self.class_name,
            "range": [self.start_line, self.end_line],
            "signature": self.signature,
        }


def _find_functions_at_lines(
    tree: "Tree",
    source: bytes,
    target_lines: set[int],
    file_path: str,
) -> list[FunctionScope]:
    """Find all functions that contain any of the target lines."""
    results: list[FunctionScope] = []
    seen: set[tuple[str | None, str, int]] = set()

    def visit(node, class_name: str | None = None) -> None:
        node_type = node.type

        if node_type == "class_definition":
            name_node = node.child_by_field_name("name")
            cls_name = name_node.text.decode("utf-8") if name_node and name_node.text else None
            for child in node.children:
                visit(child, class_name=cls_name)
            return

        if node_type == "function_definition":
            start_line = node.start_point.row + 1  # 1-indexed
            end_line = node.end_point.row + 1

            # Check if any target line falls within this function
            if any(start_line <= line <= end_line for line in target_lines):
                name_node = node.child_by_field_name("name")
                func_name = name_node.text.decode("utf-8") if name_node and name_node.text else ""

                key = (class_name, func_name, start_line)
                if key not in seen:
                    seen.add(key)
                    sig = extract_signature(node, source)
                    results.append(
                        FunctionScope(
                            path=file_path,
                            function_name=func_name,
                            class_name=class_name,
                            start_line=start_line,
                            end_line=end_line,
                            signature=sig,
                        )
                    )

        for child in node.children:
            visit(child, class_name=class_name)

    visit(tree.root_node)
    return results


def extract_function_scopes(
    file_path: Path,
    line_numbers: set[int],
    *,
    relative_path: str | None = None,
) -> list[FunctionScope]:
    """Extract function scopes that contain the given line numbers.

    Args:
        file_path: Absolute path to the Python source file.
        line_numbers: Set of 1-indexed line numbers to find enclosing functions for.
        relative_path: Optional relative path to use in the output (defaults to file_path).

    Returns:
        List of FunctionScope objects for functions containing any target lines.
    """
    if not file_path.exists() or not file_path.suffix == ".py":
        return []

    if not line_numbers:
        return []

    try:
        source = file_path.read_bytes()
    except OSError:
        return []

    parser = get_parser()
    tree = parser.parse(source)

    if tree.root_node.has_error:
        return []

    output_path = relative_path if relative_path else str(file_path)
    return _find_functions_at_lines(tree, source, line_numbers, output_path)
