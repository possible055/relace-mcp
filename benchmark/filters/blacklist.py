"""Blacklist of functions that should be excluded from Soft Context.

These are typically:
- Python builtins (print, len, str, etc.)
- Standard library utilities
- Common patterns that appear everywhere (__init__, __str__, etc.)
- Logging and debug functions
"""

# Python builtins
BUILTINS = frozenset(
    {
        "abs",
        "aiter",
        "all",
        "anext",
        "any",
        "ascii",
        "bin",
        "bool",
        "breakpoint",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "classmethod",
        "compile",
        "complex",
        "delattr",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "eval",
        "exec",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "globals",
        "hasattr",
        "hash",
        "help",
        "hex",
        "id",
        "input",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "locals",
        "map",
        "max",
        "memoryview",
        "min",
        "next",
        "object",
        "oct",
        "open",
        "ord",
        "pow",
        "print",
        "property",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "setattr",
        "slice",
        "sorted",
        "staticmethod",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "vars",
        "zip",
        "__import__",
    }
)

# Common dunder methods
DUNDER_METHODS = frozenset(
    {
        "__init__",
        "__new__",
        "__del__",
        "__repr__",
        "__str__",
        "__bytes__",
        "__format__",
        "__lt__",
        "__le__",
        "__eq__",
        "__ne__",
        "__gt__",
        "__ge__",
        "__hash__",
        "__bool__",
        "__getattr__",
        "__getattribute__",
        "__setattr__",
        "__delattr__",
        "__dir__",
        "__get__",
        "__set__",
        "__delete__",
        "__set_name__",
        "__init_subclass__",
        "__class_getitem__",
        "__call__",
        "__len__",
        "__length_hint__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__missing__",
        "__iter__",
        "__reversed__",
        "__contains__",
        "__add__",
        "__sub__",
        "__mul__",
        "__matmul__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__divmod__",
        "__pow__",
        "__lshift__",
        "__rshift__",
        "__and__",
        "__xor__",
        "__or__",
        "__neg__",
        "__pos__",
        "__abs__",
        "__invert__",
        "__complex__",
        "__int__",
        "__float__",
        "__index__",
        "__round__",
        "__trunc__",
        "__floor__",
        "__ceil__",
        "__enter__",
        "__exit__",
        "__await__",
        "__aiter__",
        "__anext__",
        "__aenter__",
        "__aexit__",
    }
)

# Common utility/logging function names
UTILITY_FUNCTIONS = frozenset(
    {
        # Logging
        "log",
        "debug",
        "info",
        "warning",
        "error",
        "critical",
        "exception",
        "logger",
        "logging",
        "get_logger",
        # Common utilities
        "copy",
        "deepcopy",
        "clone",
        "validate",
        "check",
        "verify",
        "assert_",
        "to_dict",
        "from_dict",
        "to_json",
        "from_json",
        "serialize",
        "deserialize",
        "encode",
        "decode",
        "format",
        "parse",
        "stringify",
        # Testing
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
        "test_",
        "mock_",
        "patch_",
        "fixture",
    }
)

# Prefixes that indicate utility functions
UTILITY_PREFIXES = (
    "_validate_",
    "_check_",
    "_assert_",
    "_log_",
    "_debug_",
    "_format_",
    "_parse_",
    "get_",
    "set_",
    "is_",
    "has_",
)

# Combined blacklist
ALL_BLACKLISTED = BUILTINS | DUNDER_METHODS | UTILITY_FUNCTIONS


def is_blacklisted(function_name: str) -> bool:
    """Check if a function name should be excluded from Soft Context.

    Args:
        function_name: Name of the function to check.

    Returns:
        True if the function should be excluded.
    """
    if not function_name:
        return True

    # Exact match
    if function_name in ALL_BLACKLISTED:
        return True

    # Dunder check (any __xxx__)
    if function_name.startswith("__") and function_name.endswith("__"):
        return True

    # Prefix check for utility functions
    lower_name = function_name.lower()
    for prefix in UTILITY_PREFIXES:
        if lower_name.startswith(prefix):
            return True

    # Test functions
    if lower_name.startswith("test_"):
        return True

    return False
