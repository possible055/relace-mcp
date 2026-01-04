"""Call graph analysis for soft ground truth expansion.

Uses tree-sitter to analyze Python files and extract function call relationships.
This enables expanding ground truth to include callee functions that may be
relevant context for understanding the code change.

Supports both local (GT files only) and global (entire repo) call graph analysis.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from ..filters.blacklist import is_blacklisted
from .treesitter import TREE_SITTER_AVAILABLE, extract_signature, get_parser


class FunctionDef(NamedTuple):
    name: str
    start_line: int
    end_line: int
    calls: list[str]  # Function names called within this function


class CallGraphResult(NamedTuple):
    functions: dict[str, FunctionDef]  # name -> FunctionDef


def _extract_name(node) -> str | None:
    """Extract name from identifier or attribute node."""
    if node is None:
        return None
    if node.type == "identifier":
        return node.text.decode("utf-8") if node.text else None
    if node.type == "attribute":
        # a.b.c -> return "c" (the function name)
        for child in node.children:
            if child.type == "identifier":
                last_name = child.text.decode("utf-8") if child.text else None
        return last_name if "last_name" in dir() else None
    return None


def _extract_function_calls(node, calls: list[str]) -> None:
    """Recursively extract function call names from AST node."""
    if node.type == "call":
        # Get the function being called
        func_node = node.child_by_field_name("function")
        if func_node:
            name = _extract_name(func_node)
            if name and name not in calls:
                calls.append(name)

    for child in node.children:
        _extract_function_calls(child, calls)


def _parse_function_def(node) -> FunctionDef | None:
    """Parse a function_definition node into FunctionDef."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None

    name = name_node.text.decode("utf-8") if name_node.text else None
    if not name:
        return None

    # Extract function calls within this function
    calls: list[str] = []
    body_node = node.child_by_field_name("body")
    if body_node:
        _extract_function_calls(body_node, calls)

    # tree-sitter uses 0-indexed lines
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1

    return FunctionDef(name=name, start_line=start_line, end_line=end_line, calls=calls)


def analyze_file(file_path: Path) -> CallGraphResult | None:
    """Analyze a Python file and extract call graph information.

    Args:
        file_path: Path to the Python file.

    Returns:
        CallGraphResult with function definitions, or None on error.
    """
    if not TREE_SITTER_AVAILABLE:
        return None

    if not file_path.exists() or not file_path.suffix == ".py":
        return None

    try:
        content = file_path.read_bytes()
    except Exception:
        return None

    parser = get_parser()
    tree = parser.parse(content)

    functions: dict[str, FunctionDef] = {}

    def visit_functions(node):
        if node.type == "function_definition":
            func_def = _parse_function_def(node)
            if func_def:
                functions[func_def.name] = func_def

        # Also check for methods inside classes
        if node.type == "class_definition":
            for child in node.children:
                if child.type == "block":
                    for block_child in child.children:
                        if block_child.type == "function_definition":
                            func_def = _parse_function_def(block_child)
                            if func_def:
                                functions[func_def.name] = func_def

        for child in node.children:
            visit_functions(child)

    visit_functions(tree.root_node)
    return CallGraphResult(functions=functions)


def expand_ground_truth(
    repo_path: Path,
    ground_truth_files: dict[str, list[tuple[int, int]]],
    *,
    max_depth: int = 1,
) -> dict[str, list[tuple[int, int]]]:
    """Expand ground truth by including called functions.

    For each function in the ground truth, find the functions it calls
    and add them to the soft ground truth.

    Args:
        repo_path: Root path of the repository.
        ground_truth_files: Original ground truth (path -> line ranges).
        max_depth: Maximum call depth to expand (1 = direct calls only).

    Returns:
        Expanded ground truth including called functions.
    """
    if not TREE_SITTER_AVAILABLE:
        return {}

    # Build a map of all functions in the repo (only GT files for now)
    all_functions: dict[str, dict[str, tuple[str, FunctionDef]]] = {}  # file -> name -> (path, def)

    for file_path in ground_truth_files:
        full_path = repo_path / file_path
        result = analyze_file(full_path)
        if result:
            all_functions[file_path] = {
                name: (file_path, func_def) for name, func_def in result.functions.items()
            }

    # Find which functions are in ground truth ranges
    gt_functions: list[tuple[str, FunctionDef]] = []
    for file_path, ranges in ground_truth_files.items():
        if file_path not in all_functions:
            continue
        for _name, (_path, func_def) in all_functions[file_path].items():
            for start, end in ranges:
                if func_def.start_line <= end and func_def.end_line >= start:
                    gt_functions.append((file_path, func_def))
                    break

    # Collect called function names
    called_names: set[str] = set()
    for _, func_def in gt_functions:
        called_names.update(func_def.calls)

    # Find definitions of called functions
    soft_gt: dict[str, list[tuple[int, int]]] = {}

    for file_path, funcs in all_functions.items():
        for name, (path, func_def) in funcs.items():
            if name in called_names and (path, func_def) not in gt_functions:
                if file_path not in soft_gt:
                    soft_gt[file_path] = []
                soft_gt[file_path].append((func_def.start_line, func_def.end_line))

    return soft_gt


# =============================================================================
# Global Call Graph Index
# =============================================================================


@dataclass
class GlobalFunctionDef:
    """Function definition with full context for global indexing."""

    name: str
    file_path: str  # Relative path from repo root
    class_name: str | None
    start_line: int
    end_line: int
    calls: list[str]  # Function names called within this function
    signature: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "class_name": self.class_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "calls": self.calls,
            "signature": self.signature,
        }


@dataclass
class GlobalCallGraph:
    """Global call graph index for an entire repository."""

    functions: dict[str, list[GlobalFunctionDef]] = field(default_factory=dict)
    callers: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    callees: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    file_map: dict[str, str] = field(default_factory=dict)

    def add_function(self, func: GlobalFunctionDef) -> None:
        """Add a function to the index."""
        if func.name not in self.functions:
            self.functions[func.name] = []
        self.functions[func.name].append(func)
        self.file_map[func.name] = func.file_path

        # Build caller/callee relationships
        for callee_name in func.calls:
            if not is_blacklisted(callee_name):
                self.callees[func.name].add(callee_name)
                self.callers[callee_name].add(func.name)

    def get_function_defs(self, name: str) -> list[GlobalFunctionDef]:
        """Get all definitions of a function by name."""
        return self.functions.get(name, [])

    def get_callers(self, name: str) -> set[str]:
        """Get all functions that call the given function."""
        return self.callers.get(name, set())

    def get_callees(self, name: str) -> set[str]:
        """Get all functions called by the given function."""
        return self.callees.get(name, set())


def _analyze_file_global(
    file_path: Path,
    relative_path: str,
    source: bytes,
) -> list[GlobalFunctionDef]:
    """Analyze a single file for global indexing."""
    if not TREE_SITTER_AVAILABLE:
        return []

    parser = get_parser()
    tree = parser.parse(source)
    functions: list[GlobalFunctionDef] = []

    def visit(node, class_name: str | None = None) -> None:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            cls_name = name_node.text.decode("utf-8") if name_node and name_node.text else None
            for child in node.children:
                visit(child, class_name=cls_name)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                for child in node.children:
                    visit(child, class_name=class_name)
                return

            func_name = name_node.text.decode("utf-8") if name_node.text else ""
            if not func_name:
                for child in node.children:
                    visit(child, class_name=class_name)
                return

            # Extract calls
            calls: list[str] = []
            body_node = node.child_by_field_name("body")
            if body_node:
                _extract_function_calls(body_node, calls)

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            signature = extract_signature(node, source)

            functions.append(
                GlobalFunctionDef(
                    name=func_name,
                    file_path=relative_path,
                    class_name=class_name,
                    start_line=start_line,
                    end_line=end_line,
                    calls=calls,
                    signature=signature,
                )
            )

        for child in node.children:
            visit(child, class_name=class_name)

    visit(tree.root_node)
    return functions


def build_global_index(
    repo_path: Path,
    *,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> GlobalCallGraph:
    """Build a global call graph index for the entire repository.

    Args:
        repo_path: Root path of the repository.
        include_patterns: Glob patterns for files to include (default: ["**/*.py"]).
        exclude_patterns: Glob patterns for files to exclude.

    Returns:
        GlobalCallGraph with all functions indexed.
    """
    if not TREE_SITTER_AVAILABLE:
        return GlobalCallGraph()

    if include_patterns is None:
        include_patterns = ["**/*.py"]

    if exclude_patterns is None:
        exclude_patterns = [
            "**/test_*.py",
            "**/*_test.py",
            "**/tests/**",
            "**/test/**",
            "**/__pycache__/**",
            "**/venv/**",
            "**/.venv/**",
            "**/node_modules/**",
            "**/build/**",
            "**/dist/**",
        ]

    graph = GlobalCallGraph()

    # Collect all Python files
    all_files: set[Path] = set()
    for pattern in include_patterns:
        all_files.update(repo_path.glob(pattern))

    # Filter out excluded files
    def is_excluded(path: Path) -> bool:
        rel_str = str(path.relative_to(repo_path))
        for pattern in exclude_patterns or []:
            if path.match(pattern):
                return True
            # Manual check for ** patterns
            if "**" in pattern:
                import fnmatch

                if fnmatch.fnmatch(rel_str, pattern):
                    return True
        return False

    # Process each file
    for file_path in sorted(all_files):
        if is_excluded(file_path):
            continue

        try:
            source = file_path.read_bytes()
        except OSError:
            continue

        relative_path = str(file_path.relative_to(repo_path))
        functions = _analyze_file_global(file_path, relative_path, source)

        for func in functions:
            graph.add_function(func)

    return graph


def is_wrapper_function(func: GlobalFunctionDef) -> bool:
    """Detect simple wrapper functions.

    A wrapper is identified by:
    - Very short body (3 lines or less)
    - Only calls one other function

    Args:
        func: Function definition to check.

    Returns:
        True if the function appears to be a simple wrapper.
    """
    body_lines = func.end_line - func.start_line
    # Filter out blacklisted calls to get meaningful calls
    meaningful_calls = [c for c in func.calls if not is_blacklisted(c)]
    return body_lines <= 3 and len(meaningful_calls) == 1


def get_context_functions(
    graph: GlobalCallGraph,
    seed_functions: list[str],
    *,
    include_callers: bool = True,
    include_callees: bool = True,
    max_depth: int = 1,
) -> list[GlobalFunctionDef]:
    """Expand seed functions to their call context.

    Args:
        graph: Global call graph index.
        seed_functions: List of function names to expand from.
        include_callers: Include functions that call the seed functions.
        include_callees: Include functions called by the seed functions.
        max_depth: Maximum depth to traverse (1 = direct only).

    Returns:
        List of GlobalFunctionDef for context functions.
    """
    context_names: set[str] = set()
    seed_set = set(seed_functions)

    current_level = set(seed_functions)

    for _ in range(max_depth):
        next_level: set[str] = set()

        for func_name in current_level:
            if include_callees:
                for callee in graph.get_callees(func_name):
                    if callee not in seed_set and not is_blacklisted(callee):
                        next_level.add(callee)

            if include_callers:
                for caller in graph.get_callers(func_name):
                    if caller not in seed_set and not is_blacklisted(caller):
                        next_level.add(caller)

        context_names.update(next_level)
        current_level = next_level

    # Collect function definitions
    results: list[GlobalFunctionDef] = []
    for name in context_names:
        results.extend(graph.get_function_defs(name))

    return results
