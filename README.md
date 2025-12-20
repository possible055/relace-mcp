# Relace MCP Server

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Unofficial** — Personal project, not affiliated with Relace.
>
> **Built with AI** — Developed entirely with AI assistance (Antigravity, Codex, Cursor, Github Copilot, Windsurf).

MCP server for [Relace](https://www.relace.ai/) — AI-powered instant code merging and agentic codebase search.

## Features

- **Fast Apply** — Apply code edits at 10,000+ tokens/sec via Relace API
- **Fast Search** — Agentic codebase exploration with natural language queries
- **Cloud Sync** — Upload local codebase to Relace Cloud for semantic search
- **Cloud Search** — Semantic code search over cloud-synced repositories

## Quick Start

1. Get your API key from [Relace Dashboard](https://app.relace.ai/settings/billing)

2. Add to your MCP config:

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/absolute/path/to/your/project"
      }
    }
  }
}
```

> **Important:** `RELACE_BASE_DIR` must be set to your project's absolute path. This restricts file access scope and ensures correct operation.

## Tools

### `fast_apply`

Apply edits to a file (or create a new file). Use truncation placeholders like `// ... existing code ...` or `# ... existing code ...`.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | Absolute path within `RELACE_BASE_DIR` |
| `edit_snippet` | ✅ | Code with abbreviation placeholders |
| `instruction` | ❌ | Hint for disambiguation |

**Example:**

```json
{
  "path": "/home/user/project/src/file.py",
  "edit_snippet": "// ... existing code ...\nfunction newFeature() {}\n// ... existing code ...",
  "instruction": "Add new feature"
}
```

**Returns:** UDiff of changes, or confirmation for new files.

### `fast_search`

Search the codebase and return relevant files and line ranges.

**Parameters:** `query` — Natural language search query

**Example response:**

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

**Parameters:**
- `query` — Natural language search query

### `cloud_sync`

Synchronize local codebase to Relace Cloud for semantic search. Uploads source files from `RELACE_BASE_DIR` to Relace Repos.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `force` | ❌ | `false` | Force full sync, ignoring cached state |
| `mirror` | ❌ | `false` | With `force=True`, completely overwrite cloud repo |

**Behavior:**
- Respects `.gitignore` patterns (uses `git ls-files` when available)
- Supports 60+ common source code file types (`.py`, `.js`, `.ts`, `.java`, etc.)
- Skips files > 1MB and common non-source directories (`node_modules`, `__pycache__`, etc.)
- Sync state stored in `~/.local/state/relace/sync/`

<details>
<summary>Sync Modes (Advanced)</summary>

| Mode | Trigger | Description |
|------|---------|-------------|
| Incremental | (default) | Only uploads new/modified files, deletes removed files |
| Safe Full | `force=True`, first sync, or HEAD changed | Uploads all files; suppresses deletes unless HEAD changed |
| Mirror Full | `force=True, mirror=True` | Completely overwrites cloud to match local |

**HEAD Change Detection:** When git HEAD changes since last sync (e.g., branch switch, rebase, commit amend), Safe Full mode automatically cleans up zombie files from the old ref to prevent stale search results.

</details>

### `cloud_search`

Semantic code search over the cloud-synced repository. Requires running `cloud_sync` first.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | ✅ | — | Natural language search query |
| `branch` | ❌ | `""` | Branch to search (empty uses API default) |
| `score_threshold` | ❌ | `0.3` | Minimum relevance score (0.0-1.0) |
| `token_limit` | ❌ | `30000` | Maximum tokens to return |

### `cloud_list`

List all repositories in your Relace Cloud account.

**Parameters:** None

### `cloud_info`

Get detailed sync status for the current repository. Use before `cloud_sync` to understand what action is needed.

**Parameters:** None

### `cloud_clear`

Delete the cloud repository and local sync state. Use when switching projects or resetting after major restructuring.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `confirm` | ✅ | `false` | Must be `true` to proceed (safety guard) |

**Returns:**

```json
{
  "deleted": true,
  "repo_id": "uuid",
  "state_cleared": true
}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RELACE_API_KEY` | ✅ | API key from [Relace Dashboard](https://app.relace.ai/settings/billing) |
| `RELACE_BASE_DIR` | ✅ | Absolute path to project root |
| `RELACE_STRICT_MODE` | ❌ | Set `1` to require explicit base dir (recommended for production) |

<details>
<summary>Advanced Settings</summary>

### Developer Overrides

These settings allow temporary overrides when the official API updates before the package catches up:

| Variable | Default |
|----------|---------|
| `RELACE_ENDPOINT` | `https://instantapply.endpoint.relace.run/v1/code/apply` |
| `RELACE_MODEL` | `relace-apply-3` |
| `RELACE_TIMEOUT_SECONDS` | `60` |
| `RELACE_MAX_RETRIES` | `3` |
| `RELACE_RETRY_BASE_DELAY` | `1.0` |
| `RELACE_SEARCH_ENDPOINT` | `https://search.endpoint.relace.run/v1/search/chat/completions` |
| `RELACE_SEARCH_MODEL` | `relace-search` |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `120` |
| `RELACE_SEARCH_MAX_TURNS` | `6` |
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` |
| `RELACE_REPO_ID` | — (pre-configured repo UUID to skip list/create) |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` |

### Fast Search Provider Swap

Switch to OpenAI-compatible providers for `fast_search`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_SEARCH_PROVIDER` | `relace` | Set to `openai` for OpenAI-compatible mode |
| `OPENAI_API_KEY` | — | Required when `RELACE_SEARCH_PROVIDER=openai` |

### Fast Search Tool Control

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_SEARCH_ENABLED_TOOLS` | — | Comma-separated allowlist (`view_file`, `view_directory`, `grep_search`, `glob`, `bash`). `report_back` is always enabled. |
| `RELACE_SEARCH_PARALLEL_TOOL_CALLS` | `1` | Enable parallel tool calls for lower latency |

</details>

<details>
<summary>Remote Deployment (Streamable HTTP)</summary>

For remote deployment, run with streamable-http transport:

```bash
relace-mcp -t streamable-http -p 8000
```

Connect via:

```json
{
  "mcpServers": {
    "relace": {
      "type": "streamable-http",
      "url": "http://your-server:8000/mcp"
    }
  }
}
```

Additional options: `--host` (default: `0.0.0.0`), `--path` (default: `/mcp`).

</details>

## Logging

> **Note:** File logging is experimental. Enable with `RELACE_EXPERIMENTAL_LOGGING=1`.

Operation logs are written to `~/.local/state/relace/relace_apply.log`.

## Troubleshooting

Common issues:
- `RELACE_API_KEY is not set`: set the key in your environment or MCP config.
- `RELACE_BASE_DIR does not exist` / `INVALID_PATH`: ensure the path exists and is within `RELACE_BASE_DIR`.
- `NEEDS_MORE_CONTEXT`: include 1–3 real anchor lines before and after the target block.

## Development

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync
uv run pytest
```
