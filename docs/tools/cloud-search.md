# Cloud Search

Semantic search over a cloud-synced repository.

## Overview

Cloud Search enables semantic code search over a repository synced to Relace Cloud.

This tool operates on the repository derived from your current base directory (via `MCP_BASE_DIR` or MCP Roots).

## Prerequisites

1. **Enable cloud tools**: Set `RELACE_CLOUD_TOOLS=1`
2. **API key**: Set `RELACE_API_KEY`
3. **Restart**: Restart your MCP client

## Quick Start

### 1. Sync Your Repository

First, sync your codebase to the cloud:

```python
cloud_sync(force=False, mirror=False)
```

**Returns:**

```json
{
  "trace_id": "a1b2c3d4",
  "repo_id": "r_...",
  "repo_head": "abc123...",
  "sync_mode": "incremental",
  "files_created": 42,
  "files_updated": 0,
  "files_deleted": 0,
  "files_skipped": 108,
  "warnings": []
}
```

### 2. Search Your Repository

Search using natural language:

```python
cloud_search(query="authentication middleware")
```

**Returns:**

```json
{
  "trace_id": "a1b2c3d4",
  "query": "authentication middleware",
  "branch": "",
  "hash": "abc123...",
  "repo_id": "r_...",
  "result_count": 1,
  "results": [
    {
      "filename": "src/middleware/auth.py",
      "score": 0.95,
      "content": "class AuthMiddleware: ..."
    }
  ],
  "warnings": []
}
```

## Cloud Tools

### cloud_sync

Upload your codebase for semantic indexing.

**Parameters:**

- `force` (bool): Re-upload all files (default: `False`)
- `mirror` (bool): Delete cloud files not in local (default: `False`)

**Examples:**

```python
# Incremental sync (default)
cloud_sync()

# Force full re-sync
cloud_sync(force=True)

# Mirror mode (dangerous!)
cloud_sync(force=True, mirror=True)
```

### cloud_search

Search within the synced repository.

**Parameters:**

- `query` (str): Natural language search query
- `branch` (str, optional): Branch to search (empty string uses API default)

**Examples:**

```python
# Basic search
cloud_search(query="user authentication")

# Specific search
cloud_search(query="JWT token validation in middleware")

# Cross-cutting concerns
cloud_search(query="error handling for database timeouts")
```

### cloud_info

Get sync status and repository information.

**Parameters:**

- `reason` (str): Why you're checking (for logging)

**Example:**

```python
cloud_info(reason="checking sync status before search")
```

**Returns:**

```json
{
  "trace_id": "a1b2c3d4",
  "repo_name": "my-repo",
  "cloud_repo_name": "my-repo__fp",
  "local": { "git_branch": "main", "git_head": "abc12345", "git_dirty": false },
  "synced": { "repo_id": "r_...", "repo_head": "abc12345", "tracked_files": 150 },
  "cloud": { "repo_id": "r_...", "name": "my-repo__fp", "auto_index": true },
  "status": { "needs_sync": false, "ref_changed": false, "recommended_action": null },
  "warnings": []
}
```

### cloud_list

List all repositories in your Relace Cloud account.

**Example:**

```python
cloud_list(reason="checking available repos")
```

**Returns:**

```json
{
  "trace_id": "a1b2c3d4",
  "count": 2,
  "repos": [
    { "repo_id": "r_...", "name": "my-repo", "auto_index": true },
    { "repo_id": "r_...", "name": "another-repo", "auto_index": false }
  ],
  "has_more": false
}
```

### cloud_clear

Delete cloud repository and local sync state.

!!! danger "Irreversible Operation"
    This permanently deletes the cloud repository. Cannot be undone.

**Parameters:**

- `confirm` (bool): Must be `True` to proceed
- `repo_id` (str, optional): Specific repo to delete

**Example:**

```python
# Delete current repo
cloud_clear(confirm=True)

# Delete specific repo
cloud_clear(confirm=True, repo_id="r_...")
```

## Sync Modes

### Incremental Sync (Default)

Only uploads new/changed files:

```python
cloud_sync()
```

- Fast
- Efficient
- Recommended for daily use

### Force Sync

Re-uploads all files:

```python
cloud_sync(force=True)
```

- Slower
- Use after major changes
- Rebuilds entire index

### Mirror Sync

Deletes cloud files not in local:

```python
cloud_sync(force=True, mirror=True)
```

!!! warning "Use with Caution"
    Mirror mode deletes cloud files that don't exist locally. Use only when you're sure.

## Best Practices

### 1. Sync Before Search

Always sync before searching:

```python
# Check sync status
cloud_info(reason="before search")

# Sync if needed
cloud_sync()

# Now search
cloud_search(query="...")
```

### 2. Incremental Syncs

Sync incrementally during development:

```python
# After making changes
cloud_sync()  # Fast, only uploads changes
```

### 3. Monitor Sync Status

Check sync status regularly:

```python
info = cloud_info(reason="daily check")
if info["status"]["needs_sync"]:
    cloud_sync()
```

## Use Cases

### Multi-Repo Projects

Search across related repositories by syncing and searching each repository independently:

```python
# In each repo:
cloud_sync()
cloud_search(query="shared authentication logic")
```

### Code Reuse

Find reusable code across projects:

```python
cloud_search(query="retry decorator with exponential backoff")
```

### Architecture Review

Understand patterns across codebases:

```python
cloud_search(query="database migration scripts")
```

## Performance

Performance depends on file count, network, and Relace Cloud load. Initial sync is typically much slower than incremental syncs.

## Troubleshooting

??? question "Sync failing?"

    1. Check API key is set
    2. Verify network connection
    3. Check repository is a git repo
    4. Enable debug logging: `MCP_LOG_LEVEL=DEBUG`

??? question "Search not finding results?"

    1. Ensure repository is synced
    2. Try broader query
    3. Check sync status with `cloud_info`
    4. Re-sync with `cloud_sync(force=True)`

??? question "Tools not available?"

    1. Set `RELACE_CLOUD_TOOLS=1`
    2. Set `RELACE_API_KEY`
    3. Restart MCP client

## Next Steps

- [Agentic Search](agentic-search.md) - Local search
- [Fast Apply](fast-apply.md) - Apply changes
- [Configuration](../configuration/overview.md) - Advanced config
