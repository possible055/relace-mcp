# Tools Reference

This document covers the public top-level MCP tools plus the search-only internal subtools that can be enabled inside `agentic_search` / `agentic_retrieval`.

## Search Behavior

The live local exploration used by `agentic_search` and `agentic_retrieval` has a few user-visible guarantees:

- `.gitignore` filtering stays in effect during text search, so ignored trees do not reappear when the planner broadens file scope.
- Exact-text probes automatically use fixed-string matching when regex features are unnecessary, improving common search latency without changing results.

## Search-Only Subtools

`agentic_search` and `agentic_retrieval` use internal exploration tools while they work. These do not appear as standalone top-level MCP tools in `list_tools()`.

Always enabled inside search runs:
- `view_file`
- `view_directory`
- `grep_search`
- `report_back`

Optional internal subtools:
- `bash`: enable with `SEARCH_BASH_TOOLS=1`; exposed only when a `bash` executable is available on the host.
- `find_symbol`, `search_symbol`: enable with `SEARCH_LSP_TOOLS=1`; exposed only when the current project has a supported LSP language.

## `fast_apply`

Apply edits to a file (or create a new file). Use truncation placeholders like `// ... existing code ...` or `# ... existing code ...`.

Notes:
- For existing files, always include 1-2 verbatim anchor lines copied from the target file near the edit location.
- Truncation markers are recommended for larger scoped edits, but anchor-only edits are still supported.
- Outer markdown fences are preserved for `.md` / `.mdx` targets so fenced code blocks can be inserted verbatim.
- For new files, provide the complete file content and do not include truncation markers.
- Context-only omission syntax no longer triggers `APPLY_NOOP` by itself; `APPLY_NOOP` is reserved for explicit remove directives or concrete new lines that should have changed the file.
- Omission-style deletion detection remains part of opt-in semantic validation via `APPLY_SEMANTIC_CHECK=1`; it is not enabled by default because context-only adjacency can produce extra failures.
- Explicit `// remove X` / `# remove X` directives can allow large deletion-dominant edits to bypass the truncation and blast-radius guards instead of hard-failing.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | Absolute path, or a path relative to `MCP_BASE_DIR`. If `MCP_BASE_DIR` is unset, relative paths resolve against the active MCP root. |
| `edit_snippet` | ✅ | Code with abbreviation placeholders |
| `instruction` | ❌ | Hint for disambiguation |

### Example

```json
{
  "path": "/home/user/project/src/file.py",
  "edit_snippet": "// ... existing code ...\nfunction newFeature() {}\n// ... existing code ...",
  "instruction": "Add new feature"
}
```

### Returns

Returns a structured object.

- Success fields: `status`, `message`, `path`, `trace_id`, `timing_ms`, and `diff` (`null` for new files or no-op).
- Error fields: the same envelope plus `code` and optional detail fields.

### Common Errors

- `NEEDS_MORE_CONTEXT`: Anchor lines could not be located in the file.
- `APPLY_NOOP`: Merge returned an identical file even though the snippet contained explicit remove directives or concrete new lines not present in the original file.
- `MARKER_LEAKAGE`: Placeholder markers leaked into merged output (treated as literal text).
- `TRUNCATION_DETECTED`: Merged output shrank drastically and no explicit remove directive was provided.
- `BLAST_RADIUS_EXCEEDED`: Diff scope too large; split into smaller edits. Large deletion-dominant edits with explicit remove directives bypass this guard.

---

## `agentic_search`

Search the codebase and return relevant files and line ranges. Uses an agentic loop to autonomously explore the codebase.

### Behavior

- Sends periodic progress notifications during long runs.
- May return `partial=true` (and optionally `error`) when hitting `SEARCH_MAX_TURNS` or `SEARCH_TIMEOUT_SECONDS`.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |

### Example Response

```json
{
  "query": "How is authentication implemented?",
  "explanation": "Auth logic is in src/auth/...",
  "files": {
    "/home/user/project/src/auth/login.py": [[10, 80]]
  },
  "turns_used": 4,
  "partial": false
}
```

---

## `index_status`

Inspect cloud/local indexing readiness. Automatically schedules a background reindex for local backends (Codanna/ChunkHound) when their index is stale or missing.

This tool takes no parameters.

### Returns

- `relace`, `codanna`, and `chunkhound` each include `freshness`: `fresh`, `stale`, `missing`, or `unknown`
- `relace`, `codanna`, and `chunkhound` each include `hints_usable`: whether `agentic_retrieval` may use that backend's semantic hints under `prefer-stale`
- `codanna` and `chunkhound` include `background_refresh_scheduled`: `true` if a background reindex was triggered
- `background_monitor` summarizes the opt-in periodic local index monitor: whether it is active, which backend it tracks, and why it may be disabled
- For local backends, `missing` also covers bootstrap/empty index directories that do not yet contain usable index artifacts
- For Relace cloud: if stale, `status.recommended_action` tells you to run `cloud_sync()`

---

## `cloud_sync`

Available only when `RELACE_CLOUD_TOOLS=1`.

> **Note:** All `cloud_*` tools include a `trace_id` field in responses. On failures, responses may also include `status_code`, `error_code`, `retryable`, and `recommended_action`.

Synchronize local codebase to Relace Cloud for semantic search. Uploads source files from `MCP_BASE_DIR` to Relace Repos.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `force` | ❌ | `false` | Force full sync, ignoring cached state |
| `mirror` | ❌ | `false` | With `force=True`, completely overwrite cloud repo |

### Behavior

- Respects `.gitignore` patterns (uses `git ls-files` when available)
- Supports 60+ common source code file types (`.py`, `.js`, `.ts`, `.java`, etc.)
- Skips files > 1MB and common non-source directories (`node_modules`, `__pycache__`, etc.)
- Sync state stored in your platform state directory (e.g., `~/.local/state/relace/sync/` on Linux), keyed by repo name + fingerprint

> For advanced sync modes (incremental, safe full, mirror), see [advanced.md](advanced.md#sync-modes).

---

## `cloud_search`

Available only when `RELACE_CLOUD_TOOLS=1`.

Semantic code search over the cloud-synced repository. Requires running `cloud_sync` first.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |
| `branch` | ❌ | Branch to search (null = API default branch) |

> **Note:** Internal parameters (`score_threshold=0.3`, `token_limit=30000`) are not exposed to LLM.

---

## `cloud_list`

Available only when `RELACE_CLOUD_TOOLS=1`.

List all repositories in your Relace Cloud account.

This tool takes no parameters. Returns `trace_id`, `count`, `repos`, and `has_more`.
Each repo summary includes `repo_id`, `name`, `auto_index`, `created_at`, and `updated_at`.
Use to find `repo_id` for `cloud_clear`; not needed for normal search/sync workflow.

---

## `cloud_clear`

Available only when `RELACE_CLOUD_TOOLS=1`.

Delete the cloud repository and local sync state. Use when switching projects or resetting after major restructuring.

If `confirm=false`, returns `status="cancelled"` and does nothing.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `confirm` | ✅ | `false` | Must be `true` to proceed (safety guard) |
| `repo_id` | ❌ | `null` | Repo UUID to delete directly (use `cloud_list` to find). If omitted, deletes the repo for the current directory. **Note:** direct `repo_id` mode skips clearing local sync state. |

### Returns

```json
{
  "trace_id": "a1b2c3d4",
  "status": "deleted",
  "message": "Repository 'example' (uuid) and local sync state deleted successfully.",
  "repo_name": "example",
  "cloud_repo_name": "example__fingerprint",
  "repo_id": "uuid"
}
```

---

## `agentic_retrieval`

Available only when `MCP_SEARCH_RETRIEVAL=1`.

Hybrid semantic-hint + agentic code retrieval. It uses semantic hints to narrow the search space, then verifies those hints against live code exploration.

### How It Works

1. **Stage 1 — Semantic hints**: Retrieves relevant file/symbol hints from the configured backend
2. **Stage 2 — Agentic exploration**: Uses those hints to guide local grep/view exploration against the current workspace

`agentic_retrieval` never runs `cloud_sync` implicitly. Use `cloud_sync` when you want to refresh the cloud index before retrieval.

### Hint Policy

Set `MCP_RETRIEVAL_HINT_POLICY` to control how stale indexes are handled.

| Value | Default | Behavior |
|-------|---------|----------|
| `prefer-stale` | ✅ | Uses stale semantic hints when available, then verifies them against live code |
| `strict` | — | Uses semantic hints only when the selected backend is fresh |

### Backend Configuration

Set `MCP_RETRIEVAL_BACKEND` to choose a backend. Default: `relace`.

| Value | Requires | Description |
|-------|----------|-------------|
| `auto` | — | Auto-detect: prefers Codanna → ChunkHound → Relace |
| `codanna` | `codanna` CLI | Symbol-level semantic search (local, no API key needed) |
| `chunkhound` | `chunkhound` CLI + embedding API key | Chunk-level semantic search (local) |
| `relace` | `RELACE_API_KEY` | Cloud-based semantic search |
| `none` | — | Skip semantic hints entirely and run agentic-only retrieval |

#### Codanna

Symbol-level indexing — embeds function signatures and docstrings. Higher precision on implementation-level queries.

```bash
# Install
curl -fsSL --proto '=https' --tlsv1.2 https://install.codanna.sh | sh
# Or: cargo install codanna --locked
# Or: brew install codanna

# Initialize and index
cd your-project
codanna init
codanna index src

# Enable
export MCP_RETRIEVAL_BACKEND=codanna
```

> Add `.codanna/` and `.codannaignore` to your `.gitignore`.
>
> When the Codanna index is stale, `prefer-stale` still uses its hints and schedules a background refresh. `strict` skips stale Codanna hints.

#### ChunkHound

Chunk-level indexing — embeds raw code blocks. Requires an external embedding provider.

```bash
# Install
pip install chunkhound

# Index
cd your-project
chunkhound index

# Enable
export MCP_RETRIEVAL_BACKEND=chunkhound
```

Embedding provider configuration (`.chunkhound.json` in project root):

```json
{
  "embedding": {
    "provider": "openai",
    "api_key": "sk-xxx",
    "model": "text-embedding-3-small"
  }
}
```

For local Ollama (no API key needed):

```json
{
  "embedding": {
    "provider": "openai-compatible",
    "base_url": "http://localhost:11434/v1",
    "model": "qwen3-embedding:8b"
  }
}
```

> Add `.chunkhound/` and `.chunkhound.json` to your `.gitignore`.
>
> When the ChunkHound index is stale, `prefer-stale` still uses its hints and schedules a background refresh. `strict` skips stale ChunkHound hints.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | ✅ | — | Natural language query describing what to find |

### Example Response

```json
{
  "query": "How is user authentication handled?",
  "explanation": "Auth logic is in src/auth/...",
  "files": {
    "/home/user/project/src/auth/login.py": [[10, 80]]
  },
  "turns_used": 3,
  "partial": false,
  "trace_id": "a1b2c3d4",
  "semantic_hints_used": 5,
  "hint_policy": "prefer-stale",
  "hints_index_freshness": "stale",
  "background_refresh_scheduled": true
}
```
