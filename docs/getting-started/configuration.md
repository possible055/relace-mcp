# Configuration

Complete configuration guide for Relace MCP.

## Environment Variables

### Core Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RELACE_API_KEY` | Yes* | - | Relace API key from [dashboard](https://app.relace.ai/settings/billing) |
| `RELACE_BASE_URL` | No | `https://api.relace.ai` | API base URL |
| `RELACE_LOG_LEVEL` | No | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |

\* Required for `fast_apply`. Optional if only using local tools.

### Cloud Tools

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RELACE_CLOUD_TOOLS` | No | `0` | Enable cloud search tools (0 or 1) |
| `RELACE_API_KEY` | Yes** | - | Required for cloud tools |

\** Required when `RELACE_CLOUD_TOOLS=1`

### Advanced Search

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_SEARCH_RETRIEVAL` | No | `0` | Enable two-stage retrieval (0 or 1) |
| `MCP_SEARCH_TIMEOUT` | No | `30` | Search timeout in seconds |

### Performance

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RELACE_MAX_RETRIES` | No | `3` | Max API retry attempts |
| `RELACE_TIMEOUT` | No | `60` | Request timeout in seconds |

## MCP Client Configuration

### Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "sk-...",
        "RELACE_LOG_LEVEL": "INFO",
        "RELACE_CLOUD_TOOLS": "1",
        "MCP_SEARCH_RETRIEVAL": "1"
      }
    }
  }
}
```

### Claude Desktop

=== "macOS"

    Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "sk-...",
            "RELACE_CLOUD_TOOLS": "1"
          }
        }
      }
    }
    ```

=== "Windows"

    Edit `%APPDATA%\Claude\claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "sk-...",
            "RELACE_CLOUD_TOOLS": "1"
          }
        }
      }
    }
    ```

### Cline (VSCode)

Add to `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "sk-...",
        "RELACE_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

## Configuration Presets

### Minimal (Local Only)

No cloud features, local search only:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "0",
    "MCP_SEARCH_RETRIEVAL": "0"
  }
}
```

### Recommended

Balanced features and performance:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "1",
    "MCP_SEARCH_RETRIEVAL": "0",
    "RELACE_LOG_LEVEL": "INFO"
  }
}
```

### Maximum Features

All features enabled:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "1",
    "MCP_SEARCH_RETRIEVAL": "1",
    "RELACE_LOG_LEVEL": "DEBUG"
  }
}
```

### Performance Optimized

For large codebases:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "0",
    "MCP_SEARCH_TIMEOUT": "60",
    "RELACE_MAX_RETRIES": "5"
  }
}
```

## Using .env Files

Create a `.env` file in your project root:

```bash
# .env
RELACE_API_KEY=sk-...
RELACE_CLOUD_TOOLS=1
MCP_SEARCH_RETRIEVAL=1
RELACE_LOG_LEVEL=INFO
```

Then reference it in your MCP configuration:

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

!!! warning "Security"
    Never commit `.env` files with API keys to version control. Add `.env` to `.gitignore`.

## Logging

### Log Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages (default)
- **WARNING**: Warning messages
- **ERROR**: Error messages only

### View Logs

=== "Cursor"

    1. Open Developer Tools: `Cmd+Option+I` (Mac) or `Ctrl+Shift+I` (Windows)
    2. Go to Console tab
    3. Filter by "relace-mcp"

=== "Claude Desktop"

    Check application logs:

    - macOS: `~/Library/Logs/Claude/`
    - Windows: `%APPDATA%\Claude\logs\`

=== "Cline"

    1. Open Output panel: `View > Output`
    2. Select "Cline" from dropdown

## Troubleshooting

??? question "API key not working?"

    1. Verify key is correct (no extra spaces)
    2. Check [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. Ensure environment variable is set correctly
    4. Restart MCP client

??? question "Cloud tools not available?"

    1. Set `RELACE_CLOUD_TOOLS=1`
    2. Ensure API key is set
    3. Restart MCP client
    4. Check logs for errors

??? question "Slow performance?"

    1. Install `ripgrep` for faster search
    2. Increase timeouts if on slow network
    3. Disable `MCP_SEARCH_RETRIEVAL` if not needed
    4. Use local-only mode (`RELACE_CLOUD_TOOLS=0`)

## Next Steps

- [Quick Start](quick-start.md) - Start using Relace MCP
- [Tools Overview](../tools/index.md) - Learn about available tools
