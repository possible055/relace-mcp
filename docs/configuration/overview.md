# Overview

Relace MCP supports custom model providers and RAG chunked code indexing services, not limited to a single commercial service.

## Environment Variables

Use environment variables to configure features and custom providers. See [Environment Variables](../advanced/environment-variables.md) for the complete reference.

## Examples

Configuration examples for different clients.

### Codex

???+ example "Default Relace config + LSP tools + retrieval"
    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]

    [mcp_servers.relace.env]
    RELACE_API_KEY = "your_relace_api_key"
    RELACE_CLOUD_TOOLS = "1"

    # Agentic search settings
    SEARCH_LSP_TOOLS = "1"

    # Hybrid search settings
    MCP_SEARCH_MODE = "both"
    ```

??? example "Agentic search using OpenAI provider"
    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]

    [mcp_servers.relace.env]
    RELACE_API_KEY = "your_relace_api_key"
    RELACE_CLOUD_TOOLS = "1"

    # Agentic search settings
    SEARCH_PROVIDER = "openai"
    SEARCH_ENDPOINT = "https://api.openai.com/v1"
    OPENAI_API_KEY = "your_api_key"
    SEARCH_MODEL = "gpt-4o"
    SEARCH_LSP_TOOLS = "1"

    # Hybrid search settings
    MCP_SEARCH_MODE = "both"
    ```

??? example "Agentic search using OpenAI, retrieval using codanna"
    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]

    [mcp_servers.relace.env]
    RELACE_API_KEY = "your_relace_api_key"

    # Agentic search settings
    SEARCH_PROVIDER = "openai"
    SEARCH_ENDPOINT = "https://api.openai.com/v1"
    OPENAI_API_KEY = "your_openai_api_key"
    SEARCH_MODEL = "gpt-4o"
    SEARCH_LSP_TOOLS = "1"

    # Hybrid search settings
    MCP_SEARCH_MODE = "both"
    MCP_RETRIEVAL_BACKEND = "codanna"
    ```

### Cursor

???+ example "Default Relace config + LSP tools + retrieval"
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your_relace_api_key",
            "RELACE_CLOUD_TOOLS": "1",
            "SEARCH_LSP_TOOLS": "1",
            "MCP_SEARCH_MODE": "both"
          }
        }
      }
    }
    ```

??? example "Agentic search using OpenAI provider"
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your_relace_api_key",
            "RELACE_CLOUD_TOOLS": "1",
            "SEARCH_PROVIDER": "openai",
            "OPENAI_API_KEY": "your_openai_api_key",
            "SEARCH_MODEL": "gpt-4o",
            "SEARCH_LSP_TOOLS": "1",
            "MCP_SEARCH_MODE": "both"
          }
        }
      }
    }
    ```

??? example "Agentic search using OpenAI, retrieval using codanna"
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your_relace_api_key",
            "SEARCH_PROVIDER": "openai",
            "OPENAI_API_KEY": "your_openai_api_key",
            "SEARCH_MODEL": "gpt-4o",
            "SEARCH_LSP_TOOLS": "1",
            "MCP_SEARCH_MODE": "both",
            "MCP_RETRIEVAL_BACKEND": "codanna"
          }
        }
      }
    }
    ```

## See Also

- [Environment Variables](../advanced/environment-variables.md) - Complete reference
