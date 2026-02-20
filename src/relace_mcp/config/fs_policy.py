# Shared traversal prune set for search tools.
SEARCH_TRAVERSAL_PRUNE_DIRS = frozenset(
    {
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "target",
        "venv",
    }
)

# LSP scans use a broader ignore set for performance and workspace safety.
LSP_IGNORED_DIR_NAMES = SEARCH_TRAVERSAL_PRUNE_DIRS | frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".direnv",
    }
)

# Cloud sync fallback scanner excludes generated, dependency, and tool-state directories.
CLOUD_SYNC_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".npm",
        ".yarn",
        "venv",
        ".venv",
        "env",
        ".env",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",
        "out",
        ".next",
        ".nuxt",
        "coverage",
        ".coverage",
    }
)

# Encoding detection only samples likely source directories.
ENCODING_DETECTION_IGNORED_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "venv",
        ".venv",
        "dist",
        "build",
    }
)

__all__ = [
    "SEARCH_TRAVERSAL_PRUNE_DIRS",
    "LSP_IGNORED_DIR_NAMES",
    "CLOUD_SYNC_EXCLUDED_DIRS",
    "ENCODING_DETECTION_IGNORED_DIRS",
]
