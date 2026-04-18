# Tools Reference

Use `list_tools()` and `list_resources()` to discover what is available in the current session.

## `fast_apply`

Apply edits to a file or create a new file.

### Notes

- For existing files, include 1-2 verbatim anchor lines copied from the target file near the edit location.
- For new files, provide the complete file content.
- Truncation placeholders such as `// ... existing code ...` and `# ... existing code ...` are supported for larger edits.

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

Returns a structured object. On success, inspect `diff` to see the applied change.

### Common Errors

- `NEEDS_MORE_CONTEXT`: Anchor lines could not be located in the file.
- `APPLY_NOOP`: The edit did not produce a file change.
- `MARKER_LEAKAGE`: Placeholder markers leaked into merged output.
- `TRUNCATION_DETECTED`: Merged output shrank drastically without an explicit delete directive.
- `BLAST_RADIUS_EXCEEDED`: Diff scope too large; split into smaller edits.

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

## `index_status`

Available when `RELACE_CLOUD_TOOLS=1` or a local index CLI (`codanna` / `chunkhound`) is discoverable in `PATH`.

Inspect cloud/local indexing readiness.

This tool takes no parameters.

Returns readiness information for `relace`, `codanna`, and `chunkhound`, plus suggested next actions when needed.

---

## `cloud_sync`

Available only when `RELACE_CLOUD_TOOLS=1`.

Synchronize the local codebase to Relace Cloud for semantic search.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `force` | ❌ | `false` | Force full sync, ignoring cached state |
| `mirror` | ❌ | `false` | With `force=True`, completely overwrite the cloud repo |

> For sync modes (incremental, safe full, mirror), see [advanced.md](advanced.md#sync-modes).

---

## `cloud_search`

Available only when `RELACE_CLOUD_TOOLS=1`.

Semantic code search over the cloud-synced repository. Requires running `cloud_sync` first.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |
| `branch` | ❌ | Branch to search (`null` = API default branch) |

---

## `cloud_list`

Available only when `RELACE_CLOUD_TOOLS=1`.

List repositories in your Relace Cloud account. Use this to find `repo_id` for `cloud_clear`.

This tool takes no parameters.

---

## `cloud_clear`

Available only when `RELACE_CLOUD_TOOLS=1`.

Delete the cloud repository and local sync state.

If `confirm=false`, returns `status="cancelled"` and does nothing.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `confirm` | ✅ | `false` | Must be `true` to proceed |
| `repo_id` | ❌ | `null` | Repo UUID to delete directly. If omitted, deletes the repo for the current directory. |

---

## `agentic_retrieval`

Available only when `MCP_SEARCH_RETRIEVAL=1`.

Hybrid semantic-hint + code retrieval. It uses semantic hints to narrow the search space, then verifies them against live code exploration.

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
| `auto` | — | Auto-detect: prefers Codanna -> ChunkHound -> Relace |
| `codanna` | `codanna` CLI | Symbol-level semantic search (local) |
| `chunkhound` | `chunkhound` CLI + embedding API key | Chunk-level semantic search (local) |
| `relace` | `RELACE_API_KEY` | Cloud-based semantic search |
| `none` | — | Skip semantic hints entirely and run agentic-only retrieval |

For backend setup, see [advanced.md](advanced.md#local-retrieval-backends).

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
  "partial": false
}
```
