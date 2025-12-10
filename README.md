# Relace MCP Server

MCP server for [Relace](https://www.relace.ai/) — AI-powered code merging and search.

## Features

- **Fast Apply** — Apply LLM-generated diffs to local files at 10,000+ tok/s
- **Fast Search** — Agentic codebase search using Relace Search model
- **Dual transport** — STDIO (default) for IDE integration, HTTP for remote deployment
- **Create new files** — Directly write new files without API call
- **UDiff output** — Returns unified diff for agent verification
- **Path security** — Configurable base directory to prevent path traversal
- **Auto-retry** — Handles transient API errors gracefully

## Installation

### STDIO Mode (Default)

Add to your MCP config (`~/.codeium/windsurf/mcp_config.json` for Windsurf):

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

### HTTP Mode (Remote Deployment)

```json
{
  "mcpServers": {
    "relace": {
      "command": "uvx",
      "args": ["relace-mcp", "-t", "http", "-p", "8000"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/path/to/project"
      }
    }
  }
}
```

Or connect directly to a running server:

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

## CLI Options

```
relace-mcp [OPTIONS]

Options:
  -t, --transport {stdio,http,streamable-http}
                        Transport protocol (default: stdio)
  --host HOST           Host to bind for HTTP mode (default: 0.0.0.0)
  -p, --port PORT       Port to bind for HTTP mode (default: 8000)
  --path PATH           MCP endpoint path for HTTP mode (default: /mcp)
  -h, --help            Show help message
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RELACE_API_KEY` | ✅ | API key from [relace](https://app.relace.ai/settings/billing) |
| `RELACE_BASE_DIR` | ⚠️ | Restrict file access to this directory (defaults to cwd) |
| `RELACE_STRICT_MODE` | ❌ | Set to `1` to require explicit `RELACE_BASE_DIR` |

### Advanced Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_ENDPOINT` | `https://instantapply.endpoint.relace.run/v1/code/apply` | Apply API endpoint |
| `RELACE_MODEL` | `relace-apply-3` | Apply model name |
| `RELACE_SEARCH_ENDPOINT` | `https://search.endpoint.relace.run/v1/search/chat/completions` | Search API endpoint |
| `RELACE_SEARCH_MODEL` | `relace-search` | Search model name |
| `RELACE_TIMEOUT_SECONDS` | `60` | Apply request timeout |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `120` | Search request timeout |
| `RELACE_SEARCH_MAX_TURNS` | `10` | Max agent turns for search |

## Tools

### fast_apply

Apply a code edit to an existing file or create a new file.

**Inputs:**
- `file_path` (string): Absolute path to target file (UTF-8)
- `edit_snippet` (string): Code to merge, using `// ... existing code ...` placeholders
- `instruction` (string, optional): Single sentence hint for disambiguation

**Returns:**
- **Existing file**: UDiff showing changes made (for agent verification)
- **New file**: `Created {path} ({size} bytes)`
- **No changes**: `No changes made`

**Example edit_snippet:**
```javascript
// ... existing code ...

function newFeature() {
  console.log("Added by fast_apply");
}

// ... existing code ...
```

### fast_search

Run Fast Agentic Search to explore and understand the codebase.

**Inputs:**
- `query` (string): Natural language query describing what to find or understand

**Returns:**
```json
{
  "query": "How is authentication implemented?",
  "explanation": "Authentication logic is in src/auth/...",
  "files": {
    "src/auth/login.py": [[10, 80], [120, 150]],
    "src/middleware/jwt.py": [[1, 45]]
  },
  "turns_used": 4
}
```

**Typical workflow:**
1. Use `fast_search` to find relevant files
2. Review the returned file paths and line ranges
3. Use `fast_apply` to make changes

## Development

```bash
# Install dev dependencies
uv sync

# Run locally
uv run relace-mcp

# Run tests
uv run pytest
```

## Design Documentation

See [docs/design/fast_agentic_search.md](docs/design/fast_agentic_search.md) for architecture details.
