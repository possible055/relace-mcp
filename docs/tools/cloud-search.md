# Cloud Search

Semantic search across cloud-synced repositories.

## Overview

Cloud Search enables semantic code search across multiple repositories synced to Relace Cloud. Perfect for monorepo projects or searching across related codebases.

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
  "status": "synced",
  "files_uploaded": 42,
  "files_skipped": 108
}
```

### 2. Search Across Repos

Search using natural language:

```python
cloud_search(query="authentication middleware")
```

**Returns:**

```json
{
  "results": [
    {
      "file": "src/middleware/auth.py",
      "score": 0.95,
      "snippet": "class AuthMiddleware...",
      "line_range": [10, 30]
    }
  ]
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

Search across synced repositories.

**Parameters:**

- `query` (str): Natural language search query

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
  "local": {
    "branch": "main",
    "commit": "abc123..."
  },
  "synced": {
    "ref": "main@abc123",
    "files": 150
  },
  "cloud": {
    "repo_id": "r_...",
    "name": "my-repo"
  },
  "status": "synced"
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
[
  {
    "repo_id": "r_...",
    "name": "my-repo",
    "auto_index": true
  },
  {
    "repo_id": "r_...",
    "name": "another-repo",
    "auto_index": false
  }
]
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
if info["status"] != "synced":
    cloud_sync()
```

## Use Cases

### Multi-Repo Projects

Search across related repositories:

```python
# Sync all repos
# (switch to each repo and run cloud_sync)

# Search all repos
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

### Sync Speed

| Repository Size | Initial Sync | Incremental |
|-----------------|--------------|-------------|
| Small (< 100 files) | ~10s | ~1s |
| Medium (< 1000 files) | ~1min | ~5s |
| Large (< 10000 files) | ~10min | ~30s |

### Search Speed

Typical search latency:

- **Simple queries**: 100-500ms
- **Complex queries**: 500ms-2s
- **Cross-repo**: 1-5s

## Troubleshooting

??? question "Sync failing?"

    1. Check API key is set
    2. Verify network connection
    3. Check repository is a git repo
    4. Enable debug logging: `RELACE_LOG_LEVEL=DEBUG`

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
- [Configuration](../getting-started/configuration.md) - Advanced config
