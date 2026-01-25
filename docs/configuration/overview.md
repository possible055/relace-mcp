# Overview

Customize Relace MCP with advanced features and providers.

## Feature Flags

Enable experimental or optional features using environment variables.

| Feature | Variable | Description |
|---|---|---|
| **Retrieval** | `MCP_SEARCH_RETRIEVAL` | Set to `1` to enable two-stage retrieval (RAG). |
| **LSP Tools** | `SEARCH_LSP_TOOLS` | Set to `1` to enable LSP-based navigation (Go to Definition). |
| **Cloud Tools** | `RELACE_CLOUD_TOOLS` | Set to `1` to enable Relace Cloud tools. |
| **Backend** | `MCP_RETRIEVAL_BACKEND` | `relace` (default), `codanna` (local), or `chunkhound`. |

## Custom Providers

Use your own API keys for model inference.

| Provider | Variable | API Key Variable |
|---|---|---|
| **OpenAI** | `APPLY_PROVIDER=openai` | `OPENAI_API_KEY` |
| **Anthropic** | `APPLY_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |

## Examples

How to apply these settings in your client.

### Codex (TOML)

Example configuration for Codex using OpenAI provider and enabling LSP tools.

```toml
[mcp_servers.relace]
command = "uv"
args = ["tool", "run", "relace-mcp"]

[mcp_servers.relace.env]
# Provider Settings
APPLY_PROVIDER = "openai"
SEARCH_PROVIDER = "openai"
OPENAI_API_KEY = "sk-..."

# Feature Flags
SEARCH_LSP_TOOLS = "1"
MCP_RETRIEVAL_BACKEND = "codanna"
```

### Cursor (JSON)

Example configuration for Cursor using Anthropic provider and enabling Retrieval.

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "your-api-key-here",
        "APPLY_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "MCP_SEARCH_RETRIEVAL": "1"
      }
    }
  }
}
```

## See Also

- [Environment Variables](../advanced/environment-variables.md) - Complete reference
