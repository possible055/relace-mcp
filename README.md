# Relace MCP Server

MCP server for [Relace Instant Apply](https://www.relace.ai/) — AI-powered code merging at 10,000+ tokens/sec.

## Features

- **High-speed merging** — Apply LLM-generated diffs to local files instantly
- **Dry-run mode** — Preview changes before writing
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

### relace_apply_file

Apply a code diff to a local source file.

**Inputs:**
- `file_path` (string): Target file path (UTF-8)
- `edit_snippet` (string): Code to merge, using `// ... existing code ...` placeholders
- `instruction` (string, optional): Natural language hint for disambiguation
- `dry_run` (boolean, optional): Preview without writing

**Returns:**
- `file_path`: Resolved path
- `merged_code_preview`: First 4000 chars of result
- `usage`: Token usage stats
- `dry_run`: Whether changes were applied

## Development

```bash
# Install dev dependencies
uv sync

# Run locally
uv run relace-mcp

# Run tests
uv run pytest
```
