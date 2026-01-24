# Configuration

Configure your MCP client to run Relace MCP.

## Common Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RELACE_API_KEY` | Yes* | — | API key for the default Relace provider |
| `RELACE_CLOUD_TOOLS` | No | `0` | Enable `cloud_*` tools |
| `MCP_SEARCH_RETRIEVAL` | No | `0` | Enable `agentic_retrieval` |
| `MCP_LOG_LEVEL` | No | `WARNING` | Log level: DEBUG, INFO, WARNING, ERROR |
| `MCP_BASE_DIR` | No | auto | Restrict file access to this directory |

\* Required when using the default Relace provider (`APPLY_PROVIDER=relace` / `SEARCH_PROVIDER=relace`, default), and required when `RELACE_CLOUD_TOOLS=1`.

For the full environment variable reference (providers, timeouts, logging, remote deployment), see [Advanced](../advanced/index.md).

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
        "RELACE_API_KEY": "your-api-key-here",
        "RELACE_CLOUD_TOOLS": "0",
        "MCP_SEARCH_RETRIEVAL": "0",
        "MCP_LOG_LEVEL": "WARNING"
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
            "RELACE_API_KEY": "your-api-key-here",
            "RELACE_CLOUD_TOOLS": "0"
          }
        }
      }
    }
    ```

=== "Windows"

    Edit `%APPDATA%\\Claude\\claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "RELACE_CLOUD_TOOLS": "0"
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
        "RELACE_API_KEY": "your-api-key-here",
        "MCP_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

## Troubleshooting

??? question "API key errors?"

    1. Verify the key is correct (no extra spaces)
    2. Check [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. If you set `APPLY_PROVIDER` / `SEARCH_PROVIDER`, ensure the corresponding `*_API_KEY` is set

??? question "Need debug logs?"

    Set `MCP_LOG_LEVEL=DEBUG` and restart your MCP client.

## Next Steps

- [Quick Start](quick-start.md) - Get started in 5 minutes
- [Tools Overview](../tools/index.md) - Learn about available tools
- [Advanced](../advanced/index.md) - Full configuration reference
