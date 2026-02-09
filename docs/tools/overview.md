# Tools

Relace MCP provides tools for AI-assisted code editing and exploration.

## fast_apply

Apply code edits (or create new files) with line-accurate merging.

**Requirements:** Set `RELACE_API_KEY` (default provider). For alternative providers, see [Advanced](../advanced/overview.md).

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | File path (absolute or relative to `MCP_BASE_DIR`) |
| `edit_snippet` | ✅ | Code with truncation placeholders |
| `instruction` | ❌ | Hint for disambiguation |

Use truncation placeholders to keep context short:

- `// ... existing code ...` (C/JS/TS)
- `# ... existing code ...` (Python/shell)

```json
{
  "path": "src/example.py",
  "edit_snippet": "# ... existing code ...\n\ndef hello():\n    print('world')\n\n# ... existing code ...",
  "instruction": "Add hello() helper"
}
```

Returns a UDiff of changes, or confirmation for new files.

!!! tip
    - Provide `instruction` when the edit location is ambiguous.
    - If you see `NEEDS_MORE_CONTEXT`, include a few real lines before/after the target.

## agentic_search

Search your codebase using natural language queries. An AI agent explores your code to find relevant files and line ranges.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |

!!! tip "Write specific queries"
    ```python
    # ✅ Good — specific and descriptive
    agentic_search(query="function that validates JWT tokens and extracts user ID")

    # ❌ Bad — too vague
    agentic_search(query="auth logic")
    ```

**Response:**

```json
{
  "files": {
    "src/auth/login.py": [[10, 50], [80, 120]],
    "src/middleware/auth.py": [[1, 30]]
  },
  "explanation": "Human-readable explanation of findings",
  "partial": false
}
```

- **`files`** — matched file paths → list of `[start_line, end_line]` ranges
- **`explanation`** — summary of what was found
- **`partial`** — `true` if search timed out before completing

## Cloud Tools

!!! info "Enable Cloud Tools"
    Set `RELACE_CLOUD_TOOLS=1` and `RELACE_API_KEY`, then restart your MCP client.

### cloud_sync

Upload your codebase for semantic indexing.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `force` | ❌ | `False` | Re-upload all files |
| `mirror` | ❌ | `False` | Delete cloud files not in local |

!!! warning "Mirror mode"
    `cloud_sync(force=True, mirror=True)` deletes cloud files that don't exist locally. Use with caution.

### cloud_search

Semantic search over a synced repository.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |
| `branch` | ❌ | Branch to search (empty = API default) |

**Response:**

```json
{
  "results": [
    {
      "filename": "src/middleware/auth.py",
      "score": 0.95,
      "content": "class AuthMiddleware: ..."
    }
  ],
  "result_count": 1
}
```

### cloud_info

Get sync status and repository information.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `reason` | ✅ | Why you're checking (for logging) |

### cloud_list

List all repositories in your Relace Cloud account.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `reason` | ✅ | Why you're checking (for logging) |

### cloud_clear

Delete cloud repository and local sync state.

!!! danger "Irreversible"
    This permanently deletes the cloud repository. Cannot be undone.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `confirm` | ✅ | Must be `True` to proceed |
| `repo_id` | ❌ | Specific repo to delete (default: current) |

## agentic_retrieval

Two-stage semantic + agentic code retrieval. Combines cloud search with local agentic exploration for complex queries.

!!! info "Enable"
    Set `MCP_SEARCH_RETRIEVAL=1` to enable this tool.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | ✅ | Natural language search query |

## Troubleshooting

??? question "No results from agentic_search?"

    1. Make query more specific
    2. Check if code exists in repository
    3. Try alternative phrasing
    4. Enable debug logging: `MCP_LOG_LEVEL=DEBUG`

??? question "Cloud sync failing?"

    1. Check API key is set
    2. Verify network connection
    3. Check repository is a git repo
    4. Enable debug logging: `MCP_LOG_LEVEL=DEBUG`

??? question "Cloud tools not available?"

    1. Set `RELACE_CLOUD_TOOLS=1`
    2. Set `RELACE_API_KEY`
    3. Restart MCP client

??? question "Slow search performance?"

    1. Install `ripgrep` for faster file scanning
    2. Make query more specific
    3. Check system resources
