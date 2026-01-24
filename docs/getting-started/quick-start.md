# Quick Start

Get up and running with Relace MCP in 5 minutes.

## Prerequisites

Before you begin, ensure you have:

- [x] [uv](https://docs.astral.sh/uv/) installed
- [x] [git](https://git-scm.com/) installed
- [x] [ripgrep](https://github.com/BurntSushi/ripgrep) (recommended)

## Installation

### Option 1: Using uv (Recommended)

```bash
uv tool install relace-mcp
```

### Option 2: Using pip

```bash
pip install relace-mcp
```

### Option 3: From source

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv pip install -e .
```

## Get API Key

!!! tip "Relace API Key"
    Get your API key from [Relace Dashboard](https://app.relace.ai/settings/billing)

## Configuration

Configure your MCP client to use Relace MCP.

=== "Cursor"

    Edit `~/.cursor/mcp.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here"
          }
        }
      }
    }
    ```

=== "Claude Desktop"

    Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here"
          }
        }
      }
    }
    ```

=== "Cline (VSCode)"

    Edit VSCode settings (`.vscode/settings.json` or User Settings):

    ```json
    {
      "mcp.servers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here"
          }
        }
      }
    }
    ```

=== "Other Clients"

    Add to your MCP client configuration:

    - **Command**: `uv`
    - **Args**: `["tool", "run", "relace-mcp"]`
    - **Environment**:
        - `RELACE_API_KEY`: your-api-key-here

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RELACE_API_KEY` | Yes* | - | Your Relace API key |
| `RELACE_CLOUD_TOOLS` | No | `0` | Enable cloud search tools |
| `MCP_SEARCH_RETRIEVAL` | No | `0` | Enable two-stage retrieval |
| `RELACE_LOG_LEVEL` | No | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

!!! note "API Key Requirement"
    `RELACE_API_KEY` is required for `fast_apply`. Optional if only using local search tools.

## Verify Installation

Restart your MCP client and verify the tools are available:

```python
# In your MCP client, you should see these tools:
- fast_apply          # Apply code edits
- agentic_search      # Search codebase
- agentic_retrieval   # Two-stage retrieval (if enabled)
- cloud_sync          # Sync to cloud (if RELACE_CLOUD_TOOLS=1)
- cloud_search        # Search cloud repos (if RELACE_CLOUD_TOOLS=1)
- cloud_info          # Cloud repo info (if RELACE_CLOUD_TOOLS=1)
- cloud_list          # List cloud repos (if RELACE_CLOUD_TOOLS=1)
- cloud_clear         # Clear cloud repo (if RELACE_CLOUD_TOOLS=1)
```

## First Steps

### 1. Search Your Codebase

Try searching for code with natural language:

```
Use agentic_search to find where authentication is handled
```

### 2. Apply Code Changes

Make changes using `fast_apply`:

```
Use fast_apply to add error handling to the authentication function
```

### 3. Enable Cloud Search (Optional)

If you need cross-repo search:

1. Set `RELACE_CLOUD_TOOLS=1`
2. Restart your MCP client
3. Sync your repository: use `cloud_sync`
4. Search across repos: use `cloud_search`

## Next Steps

- [Installation Guide](installation.md) - Detailed installation options
- [Configuration Guide](configuration.md) - Advanced configuration
- [Tools Overview](../tools/index.md) - Learn about available tools

## Troubleshooting

??? question "Tools not showing up?"

    1. Check MCP client logs
    2. Verify `uv tool list` shows `relace-mcp`
    3. Restart your MCP client
    4. Check environment variables are set correctly

??? question "API key errors?"

    1. Verify API key is correct
    2. Check [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. Ensure no extra spaces in environment variable

??? question "Slow performance?"

    1. Install `ripgrep` for faster search
    2. Check network connection
    3. Enable debug logging: `RELACE_LOG_LEVEL=DEBUG`

Need more help? [Open an issue](https://github.com/possible055/relace-mcp/issues).
