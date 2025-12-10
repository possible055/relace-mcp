# Relace MCP Server

MCP server for [Relace Instant Apply](https://www.relace.ai/) — AI-powered code merging at 10,000+ tokens/sec.

## Features

- **High-speed merging** — Apply LLM-generated diffs to local files at 10,000+ tok/s
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

## Development

```bash
# Install dev dependencies
uv sync

# Run locally
uv run relace-mcp

# Run tests
uv run pytest
```
