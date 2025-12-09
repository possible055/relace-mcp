# Relace MCP Server

MCP server for [Relace Instant Apply](https://www.relace.ai/) — AI-powered code merging at 10,000+ tokens/sec.

## Features

- **High-speed merging** — Apply LLM-generated diffs to local files at 10,000+ tok/s
- **Create new files** — Directly write new files without API call
- **UDiff output** — Returns unified diff for agent verification
- **Path security** — Configurable base directory to prevent path traversal
- **Auto-retry** — Handles transient API errors gracefully

## Installation

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
