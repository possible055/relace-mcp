# Relace MCP Server

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Unofficial** — Personal project, not affiliated with Relace.

MCP server for [Relace](https://www.relace.ai/) — AI-powered instant code merging and agentic codebase search.

## Features

- **Fast Apply** — Apply code edits at 10,000+ tokens/sec via Relace API
- **Fast Search** — Agentic codebase exploration with natural language queries

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

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RELACE_API_KEY` | ✅ | API key from [Relace Dashboard](https://app.relace.ai/settings/billing) |
| `RELACE_BASE_DIR` | ✅ | Absolute path to project root |
| `RELACE_STRICT_MODE` | ❌ | Set `1` to require explicit base dir (recommended for production) |

<details>
<summary>Advanced Settings</summary>

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
