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

## `fast_search`

Search the codebase and return relevant files and line ranges. Uses an agentic loop to autonomously explore the codebase.

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
  "turns_used": 4
}
```

---

## `cloud_sync`

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
- Sync state stored in `~/.local/state/relace/sync/`

> For advanced sync modes (incremental, safe full, mirror), see [advanced.md](advanced.md#sync-modes).

---

## `cloud_search`

Semantic code search over the cloud-synced repository. Requires running `cloud_sync` first.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | ✅ | — | Natural language search query |
| `branch` | ❌ | `""` | Branch to search (empty uses API default) |
| `score_threshold` | ❌ | `0.3` | Minimum relevance score (0.0-1.0) |
| `token_limit` | ❌ | `30000` | Maximum tokens to return |

---

## `cloud_list`

List all repositories in your Relace Cloud account.

### Parameters

None

---

## `cloud_info`

Get detailed sync status for the current repository. Use before `cloud_sync` to understand what action is needed.

### Parameters

None

---

## `cloud_clear`

Delete the cloud repository and local sync state. Use when switching projects or resetting after major restructuring.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `confirm` | ✅ | `false` | Must be `true` to proceed (safety guard) |

### Returns

```json
{
  "deleted": true,
  "repo_id": "uuid",
  "state_cleared": true
}
```
