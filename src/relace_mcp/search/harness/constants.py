# Context truncation: total messages character limit (approx 100k tokens)
MAX_TOTAL_CONTEXT_CHARS = 400000

# Read-only tools safe for parallel execution
PARALLEL_SAFE_TOOLS = frozenset(
    {
        "bash",
        "view_file",
        "view_directory",
        "grep_search",
        "find_symbol",
        "search_symbol",
    }
)

# Maximum parallel workers (official recommendation: 4-12 tool calls per turn)
MAX_PARALLEL_WORKERS = 12

# Chars Budget Tracking (reference: MorphLLM Warp Grep implementation)
# 160K chars ≈ 40K tokens, recommended context budget for search agent
MAX_CONTEXT_BUDGET_CHARS = 160_000
