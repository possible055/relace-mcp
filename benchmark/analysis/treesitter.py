"""Shared tree-sitter utilities for Python parsing.

Consolidated parser initialization and signature extraction logic.
"""

from typing import TYPE_CHECKING

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    PY_LANGUAGE = Language(tspython.language())
    _PARSER: Parser | None = None

    def get_parser() -> Parser:
        global _PARSER
        if _PARSER is None:
            _PARSER = Parser(PY_LANGUAGE)
        return _PARSER

    TREE_SITTER_AVAILABLE = True

except ImportError:
    TREE_SITTER_AVAILABLE = False
    PY_LANGUAGE = None  # type: ignore[assignment]

    def get_parser() -> "Parser":  # type: ignore[misc]
        raise ImportError("tree-sitter-python not installed")


if TYPE_CHECKING:
    from tree_sitter import Node


def extract_signature(node: "Node", source: bytes) -> str:
    """Extract function signature from the definition line.

    Args:
        node: tree-sitter function_definition node.
        source: Source file bytes.

    Returns:
        Clean function signature string without trailing colon.
    """
    start = node.start_byte
    for child in node.children:
        if child.type == "block":
            end = child.start_byte
            break
    else:
        end = node.end_byte

    sig_bytes = source[start:end].strip()
    sig = sig_bytes.decode("utf-8", errors="replace").strip()
    if sig.endswith(":"):
        sig = sig[:-1].strip()
    return " ".join(sig.split())
