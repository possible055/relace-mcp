# Context truncation: total messages character limit (approx 100k tokens)
MAX_TOTAL_CONTEXT_CHARS = 400000

# Read-only tools safe for parallel execution
PARALLEL_SAFE_TOOLS = frozenset({"view_file", "view_directory", "grep_search", "glob"})

# Maximum parallel workers (official recommendation: 4-12 tool calls per turn)
MAX_PARALLEL_WORKERS = 12

# Budget Tracker strategy thresholds (for SEARCH_MAX_TURNS=6)
BUDGET_HIGH_THRESHOLD = 4  # Remaining 4+ turns: broad exploration
BUDGET_MID_THRESHOLD = 2  # Remaining 2-3 turns: focus and prepare
# Remaining < 2 turns: report immediately

# Chars Budget Tracking (reference: MorphLLM Warp Grep implementation)
# 160K chars ≈ 40K tokens, recommended context budget for search agent
MAX_CONTEXT_BUDGET_CHARS = 160_000
