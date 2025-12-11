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
- **Dual Transport** — STDIO for IDEs, HTTP for remote deployment

## Installation

```bash
uvx relace-mcp
```

Or with pip:

```bash
pip install relace-mcp
```

## Quick Start

Add to your MCP config:

```json
{
  "mcpServers": {
    "relace": {
      "command": "uvx",
      "args": ["relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/path/to/project"
      }
    }
  }
}
```

Config locations:
- **Windsurf**: `~/.codeium/windsurf/mcp_config.json`
- **Cursor**: `~/.cursor/mcp.json`

## Tools

### `fast_apply`

Apply code edits using `// ... existing code ...` placeholders:

```javascript
// ... existing code ...

function newFeature() {
  console.log("Added by fast_apply");
}

// ... existing code ...
```

**Parameters:**
- `file_path` — Absolute path to target file
- `edit_snippet` — Code with abbreviation placeholders
- `instruction` (optional) — Hint for disambiguation

**Returns:** UDiff of changes, or confirmation for new files.

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
| `RELACE_BASE_DIR` | ⚠️ | Restrict file access (defaults to cwd) |
| `RELACE_STRICT_MODE` | ❌ | Set `1` to require explicit base dir |

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
| `RELACE_SEARCH_MAX_TURNS` | `10` |

</details>

## HTTP Mode

For remote deployment:

```bash
relace-mcp -t http -p 8000
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

## Development

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync
uv run pytest
```
