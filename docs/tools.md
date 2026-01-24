# Tools Reference

This document provides detailed information about all available MCP tools.

## `fast_apply`

Apply edits to a file (or create a new file). Use truncation placeholders like `// ... existing code ...` or `# ... existing code ...`.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | Path within `MCP_BASE_DIR` (absolute or relative) |
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

UDiff of changes, or confirmation for new files.

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

## `cloud_sync`

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

Semantic code search over the cloud-synced repository. Requires running `cloud_sync` first.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |
| `branch` | ❌ | Branch to search (empty uses API default) |

> **Note:** Internal parameters (`score_threshold=0.3`, `token_limit=30000`) are not exposed to LLM.

---

## `cloud_list`

List all repositories in your Relace Cloud account.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `reason` | ❌ | Brief explanation for LLM chain-of-thought (ignored by tool) |

---

## `cloud_info`

Get detailed sync status for the current repository. Use before `cloud_sync` to understand what action is needed.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `reason` | ❌ | Brief explanation for LLM chain-of-thought (ignored by tool) |

---

## `cloud_clear`

Delete the cloud repository and local sync state. Use when switching projects or resetting after major restructuring.

If `confirm=false`, returns `status="cancelled"` and does nothing.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `confirm` | ✅ | `false` | Must be `true` to proceed (safety guard) |

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

Two-stage semantic + agentic code retrieval. Combines semantic hints with local agentic exploration for precise results.

### Behavior

1. **Stage 1**: Loads semantic hints based on `MCP_RETRIEVAL_BACKEND`
   - `relace`: run `cloud_search`
   - `codanna`: run `codanna mcp semantic_search_with_context --json`
   - `chunkhound`: run `chunkhound search --json` (install separately: `pip install chunkhound`)
   - `none`: skip hints
2. **Stage 2**: Uses hints to guide agentic exploration (grep, view, etc.)

### Backend Configuration

#### ChunkHound (Recommended for local semantic search)

```bash
# Install chunkhound separately
pip install chunkhound

# Configure via environment variables
export MCP_RETRIEVAL_BACKEND=chunkhound
export CHUNKHOUND_EMBEDDING__PROVIDER=openai  # or voyageai, openai-compatible
export OPENAI_API_KEY=sk-xxx  # or VOYAGE_API_KEY

# Or configure via .chunkhound.json in project root
```

Example `.chunkhound.json`:
```json
{
  "embedding": {
    "provider": "openai",
    "api_key": "sk-xxx",
    "model": "text-embedding-3-small"
  }
}
```

For local Ollama:
```json
{
  "embedding": {
    "provider": "openai-compatible",
    "base_url": "http://localhost:11434/v1",
    "model": "qwen3-embedding:8b"
  }
}
```

#### Codanna

Set `MCP_RETRIEVAL_BACKEND=codanna` to use a local codanna index (run `codanna init` + `codanna index <dir>`).

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
  "cloud_hints_used": 5
}
```
