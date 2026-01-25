# Codanna Configuration

Relace MCP supports using **Codanna** as a local backend for semantic search (Retrieval).

## Prerequisite

Ensure the `codanna` CLI is installed and available in your system `PATH`.

```bash
# Verify installation
codanna --version
```

## Configuration

To enable Codanna as your retrieval backend, set the following environment variable:

```bash
export MCP_RETRIEVAL_BACKEND="codanna"
```

### Client Configuration

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "relace": {
          "env": {
            "RELACE_API_KEY": "your-key",
            "MCP_RETRIEVAL_BACKEND": "codanna",
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

=== "Claude Desktop"

    ```json
    {
      "mcpServers": {
        "relace": {
          "env": {
            "RELACE_API_KEY": "your-key",
            "MCP_RETRIEVAL_BACKEND": "codanna",
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

## Usage

When enabled, the `agentic_retrieval` tool will automatically use the local `codanna` CLI to perform searches.

Relace executes:
```bash
codanna mcp semantic_search_with_context query:YOUR_QUERY ...
```
