# Quick Start

Get started with Relace MCP in 5 minutes.

## Prerequisites

Before you begin, make sure you have:

- [x] [uv](https://docs.astral.sh/uv/) installed
- [x] [git](https://git-scm.com/) installed
- [x] [ripgrep](https://github.com/BurntSushi/ripgrep) (optional, recommended)

## Installation

### Get API Key

!!! tip "Relace API Key"
    Get your API key from the [Relace Dashboard](https://app.relace.ai/settings/billing)

### Configure

Set up your MCP client to use Relace MCP.

=== "AmpCode"

    Add to your MCP client configuration:

    - **Server Name**: `relace`
    - **Command or URL**: `uv`
    - **Arguments (whitespace-separated)**: `tool run relace-mcp`
    - **Environment Variables**:
        - `RELACE_API_KEY` = `your-api-key-here`
        - `MCP_BASE_DIR` = `/path/to/your/project`

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
          }
        }
      }
    }
    ```

=== "Claude Code"

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
          }
        }
      }
    }
    ```

=== "Codex"

    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]
    startup_timeout_sec = 30
    tool_timeout_sec = 60

    [mcp_servers.relace.env]
    RELACE_API_KEY = "your-api-key-here"
    MCP_BASE_DIR = "/path/to/your/project"
    ```

=== "Windsurf"

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
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
        - `RELACE_API_KEY` = `your-api-key-here`
        - `MCP_BASE_DIR` = `/path/to/your/project`

!!! tip "Advanced Configuration"
    For additional environment variables (cloud tools, debugging, custom providers), see [Environment Variables](../advanced/environment-variables.md).

## Verify Installation

Once configured, restart your MCP client. You should see these tools available:

- `fast_apply` - Fast code editing
- `agentic_search` - Semantic code search

For a complete list of tools and their schemas, see [Tools Overview](../tools/overview.md) and [Tool Reference](../tools/reference.md).

## Troubleshooting

??? question "Tools not showing up?"

    1. Check MCP client logs
    2. Verify `uv tool list` shows `relace-mcp`
    3. Restart your MCP client
    4. Verify environment variables are set correctly

??? question "API key errors?"

    1. Verify your API key is correct
    2. Check the [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. Ensure no extra spaces in the environment variable

??? question "Slow performance?"

    1. Install `ripgrep` for faster search
    2. Check your network connection
    3. Enable debug logs: `MCP_LOG_LEVEL=DEBUG`

Need more help? [Open an issue](https://github.com/possible055/relace-mcp/issues).

## Next Steps

- **Configuration**: See [Configuration](../configuration/overview.md) for custom providers and features
- **Environment Variables**: See [Environment Variables](../advanced/environment-variables.md) for all options
- **Tools**: Explore [Tools Overview](../tools/overview.md) to learn what Relace MCP can do
