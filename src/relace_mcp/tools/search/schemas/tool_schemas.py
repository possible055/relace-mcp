import os
import shutil
from typing import Any

from .tool_config import ToolConfigResolver

# Import tool schemas from separate module to keep this file focused on configuration
from .tool_schemas_data import _ALL_TOOL_SCHEMAS


def detect_available_lsp_servers() -> frozenset[str]:
    from relace_mcp.lsp.languages import (
        detect_available_lsp_servers as _detect_available_lsp_servers,
    )

    return _detect_available_lsp_servers()


def normalize_tool_schemas(
    schemas: list[dict[str, Any]], *, include_strict: bool
) -> list[dict[str, Any]]:
    """Normalize tool schemas by optionally removing strict field."""
    normalized: list[dict[str, Any]] = []
    for schema in schemas:
        schema_copy = dict(schema)
        func = schema_copy.get("function")
        if isinstance(func, dict):
            func_copy = dict(func)
            if not include_strict:
                func_copy.pop("strict", None)
            schema_copy["function"] = func_copy
        normalized.append(schema_copy)
    return normalized


def get_tool_schemas(
    lsp_languages: frozenset[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Get enabled tool schemas for Fast Agentic Search.

    Args:
        lsp_languages: Set of available LSP language IDs for the current project.
            If None, uses default tool set (LSP tools require explicit opt-in via SEARCH_LSP_TOOLS).
            If empty frozenset, LSP tools are hidden.
        env: Optional environment variable override for testing.

    Returns:
        List of enabled tool schemas based on configuration.
    """
    effective_env = env if env is not None else dict(os.environ)
    bash_available = shutil.which("bash") is not None

    resolver = ToolConfigResolver(
        env=effective_env,
        lsp_languages=lsp_languages,
        bash_available=bash_available,
        detect_available_lsp_servers_fn=detect_available_lsp_servers,
    )
    config = resolver.resolve()

    selected = [
        schema
        for schema in _ALL_TOOL_SCHEMAS
        if schema.get("function", {}).get("name") in config.enabled_tools
    ]
    return normalize_tool_schemas(selected, include_strict=config.include_strict)


# Default export for backward compatibility (computed at import time)
TOOL_SCHEMAS: list[dict[str, Any]] = get_tool_schemas()
