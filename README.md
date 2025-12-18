# Relace MCP Server

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Unofficial** — Personal project, not affiliated with Relace.
>
> **Built with AI** — Developed entirely with AI assistance (Antigravity, Cursor, Github Copilot, Windsurf).

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
      "command": "uvx",
      "args": ["relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/absolute/path/to/your/project"
      }
    }
  }
}
```

> **Important:** `RELACE_BASE_DIR` must be set to your project's absolute path. This restricts file access scope and ensures correct operation. Without it, the server defaults to the MCP host's startup directory (not your workspace).

> **Note:** Requires Python 3.12+. The IDE runs `uvx relace-mcp` automatically—no manual installation needed.

Config locations:
- **Cursor**: `~/.cursor/mcp.json`
- **Windsurf**: `~/.codeium/windsurf/mcp_config.json`

<details>
<summary>Why is RELACE_BASE_DIR required?</summary>

MCP servers run as separate processes spawned by the IDE. Due to current limitations:
- **Cursor** does not pass workspace directory to MCP servers via `cwd` or `roots/list`
- The server's `os.getcwd()` returns the IDE's startup directory, not your project

Setting `RELACE_BASE_DIR` explicitly ensures the server operates on the correct directory.

</details>

## Tools

### `fast_apply`

Apply code edits using truncation placeholders:
- `// ... existing code ...` (C/JS/TS-style comments)
- `# ... existing code ...` (Python/shell-style comments)

```javascript
// ... existing code ...

function newFeature() {
  console.log("Added by fast_apply");
}

// ... existing code ...
```

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | ✅ | Target file path (see [Path Formats](#path-formats)) |
| `edit_snippet` | ✅ | Code with abbreviation placeholders |
| `instruction` | ❌ | Hint for disambiguation |

**Returns:** UDiff of changes, or confirmation for new files.

#### Path Formats

`fast_apply` supports multiple path formats:

| Format | Example | Description |
|--------|---------|-------------|
| Virtual root | `/repo/src/file.py` | From `fast_search` results |
| Relative | `src/file.py` | Relative to workspace |
| Absolute | `/home/user/project/file.py` | Must be within `RELACE_BASE_DIR` |

### `fast_search`

Find relevant code with natural language:

```json
{
  "query": "How is authentication implemented?",
  "explanation": "Auth logic is in src/auth/...",
  "files": {
    "src/auth/login.py": [[10, 80], [120, 150]]
  },
  "turns_used": 4
}
```

**Parameters:**
- `query` — Natural language search query

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RELACE_API_KEY` | ✅ | API key from [Relace Dashboard](https://app.relace.ai/settings/billing) |
| `RELACE_BASE_DIR` | ✅ | Absolute path to project root (required for Cursor and most MCP clients) |
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

Operation logs are written to:

```
~/.local/state/relace/relace_apply.log
```

- JSON-line format with trace IDs
- Automatic rotation at 10 MB
- Keeps up to 5 rotated logs

## Security Considerations

- **Restrict `RELACE_BASE_DIR`**: Always set an explicit base directory in production to limit file access scope.
- **Enable Strict Mode**: Set `RELACE_STRICT_MODE=1` to require explicit base directory configuration.
- **API Key Safety**: Never commit `RELACE_API_KEY` to version control. Use environment variables or secrets management.

## Troubleshooting

<details>
<summary>Common Issues</summary>

### `RELACE_API_KEY is not set`

Ensure the API key is exported in your environment or set in the MCP config's `env` block.

### `RELACE_BASE_DIR does not exist`

The specified base directory path doesn't exist or isn't accessible. Verify the path and permissions.

### `RELACE_BASE_DIR not set` (Warning)

The server is using its startup directory as base. This is likely incorrect for your project. Set `RELACE_BASE_DIR` to your project's absolute path in the MCP config.

### `INVALID_PATH: Access denied`

The target file is outside `RELACE_BASE_DIR`. Ensure the file path is within your configured project directory.

### `API key does not start with 'rlc-'`

Your API key may be invalid. Get a valid key from [Relace Dashboard](https://app.relace.ai/settings/billing).

### `NEEDS_MORE_CONTEXT`

The edit snippet lacks sufficient anchor lines. Add 1-3 real lines of code before and after the target block.

</details>

## Development

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync
uv run pytest
```
