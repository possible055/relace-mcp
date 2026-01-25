# ChunkHound Configuration

Relace MCP supports using **ChunkHound** as a high-performance local backend for semantic search.

## Installation

Install the ChunkHound CLI:

```bash
uv tool install chunkhound
# or
pip install chunkhound
```

## Configuration

To enable ChunkHound as your retrieval backend, set the following environment variable:

```bash
export MCP_RETRIEVAL_BACKEND="chunkhound"
```

### Client Configuration

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "relace": {
          "env": {
            "RELACE_API_KEY": "your-key",
            "MCP_RETRIEVAL_BACKEND": "chunkhound",
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

## Indexing

Relace MCP handles indexing automatically.

1.  **Auto-indexing**: When you perform a search, if no index exists, Relace will attempt to generate one automatically for the current directory.
2.  **Manual indexing**: You can also run the indexer manually:

    ```bash
    cd /path/to/project
    chunkhound index
    ```
