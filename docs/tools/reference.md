# Tool Reference

This page describes the MCP tool schemas exposed by Relace MCP.

## Conventions

- `path` can be absolute, or relative to the resolved base dir (`MCP_BASE_DIR` or MCP Roots).
- `edit_snippet` supports truncation placeholders like `// ... existing code ...` and `# ... existing code ...`.

---

## `fast_apply`

Apply edits to a file (or create a new file).

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | File path (absolute or relative to `MCP_BASE_DIR`) |
| `edit_snippet` | ✅ | Code with truncation placeholders |
| `instruction` | ❌ | Hint for disambiguation |

### Returns

Structured result dict:

- On success: `status="ok"` with `path`, `diff` (UDiff or `null` for new files), `message`, `trace_id`, `timing_ms`.
- On error: `status="error"` with `code`, `message`, `path`, `trace_id`, `timing_ms`.

---

## `agentic_search`

Search the codebase and return relevant files and line ranges.

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

## `agentic_retrieval`

Two-stage semantic + agentic code retrieval.

### Behavior

1. **Stage 1**: Loads semantic hints based on `MCP_RETRIEVAL_BACKEND`
   - `relace`: uses `cloud_search` (requires cloud tools)
   - `chunkhound`: local semantic search (install separately: `pip install chunkhound`)
   - `codanna`: local codanna index
   - `none`: skip hints
2. **Stage 2**: Uses hints to guide agentic exploration.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language query describing what to find |

---

## Cloud Tools

!!! info "Enable Cloud Tools"
    Set `RELACE_CLOUD_TOOLS=1` to enable `cloud_*` tools. `RELACE_API_KEY` is required when cloud tools are enabled.

> **Note:** All `cloud_*` tools include a `trace_id` field in responses. On failures, responses may also include `status_code`, `error_code`, `retryable`, and `recommended_action`.

## `cloud_sync`

Synchronize local codebase to Relace Cloud for semantic search.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `force` | ❌ | `false` | Force full sync, ignoring cached state |
| `mirror` | ❌ | `false` | With `force=True`, delete cloud files not in local |

### Returns

Sync summary dict (fields may include):

- `trace_id`, `repo_id`, `repo_head`, `sync_mode`
- `files_created`, `files_updated`, `files_deleted`, `files_unchanged`, `files_skipped`
- `warnings` (optional), `error` (optional)

---

## `cloud_search`

Semantic code search over the cloud-synced repository. Requires running `cloud_sync` first.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |
| `branch` | ❌ | Branch to search (empty uses API default) |

### Returns

Search result dict (fields may include):

- `trace_id`, `query`, `branch`, `hash`, `repo_id`, `result_count`
- `results` (list of matches; typically includes `filename`, `score`, and `content`)
- `warnings` (optional), `error` (optional)

---

## `cloud_list`

List all repositories in your Relace Cloud account.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `reason` | ❌ | Brief explanation for LLM chain-of-thought (ignored by tool) |

### Returns

Summary dict:

- `trace_id`, `count`, `repos` (list of repo summaries), `has_more`
- `error` (optional)

---

## `cloud_info`

Get detailed sync status for the current repository. Use before `cloud_sync` to understand what action is needed.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `reason` | ❌ | Brief explanation for LLM chain-of-thought (ignored by tool) |

### Returns

Status dict:

- `trace_id`, `repo_name`, `cloud_repo_name`
- `local`, `synced`, `cloud`, `status`
- `warnings` (optional), `error` (optional)

---

## `cloud_clear`

Delete cloud repository and local sync state. Use when switching projects or resetting after major restructuring.

If `confirm=false`, returns `status="cancelled"` and does nothing.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `confirm` | ✅ | `false` | Must be `true` to proceed (safety guard) |
| `repo_id` | ❌ | — | Optional repo ID to delete directly |

### Returns

Result dict:

- `trace_id`, `status` (`cancelled`, `deleted`, `not_found`, or `error`), `message`
- `repo_id` (optional)
- `error` (optional)
