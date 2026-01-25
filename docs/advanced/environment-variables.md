# Environment Variables

Complete reference for all Relace MCP environment variables.

## Core Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RELACE_API_KEY` | Yes* | — | Relace API key from [Dashboard](https://app.relace.ai/settings/billing) |
| `MCP_BASE_DIR` | No | auto | Restrict file operations to this directory |
| `MCP_LOGGING` | No | `off` | Log mode: `off`, `safe`, `full` |

\* Required when using Relace provider (default) or when `RELACE_CLOUD_TOOLS=1`.

## Optional Features

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_CLOUD_TOOLS` | `0` | Enable cloud-based search tools (`cloud_sync`, `cloud_search`, etc.) |
| `MCP_SEARCH_RETRIEVAL` | `0` | Enable two-stage retrieval with `agentic_retrieval` tool |
| `SEARCH_LSP_TOOLS` | `0` | Enable LSP-based tools (experimental) |

## Provider Configuration

Override default providers:

| Variable | Default | Options | Description |
|----------|---------|---------|-------------|
| `APPLY_PROVIDER` | `relace` | `relace`, `openai`, `anthropic` | Code edit provider |
| `SEARCH_PROVIDER` | `relace` | `relace`, `openai`, `anthropic` | Code search provider |

When switching providers, set the corresponding API key:
- **OpenAI**: `OPENAI_API_KEY`
- **Anthropic**: `ANTHROPIC_API_KEY`

## Logging & Debugging

| Variable | Default | Options | Description |
|----------|---------|---------|-------------|
| `MCP_LOG_LEVEL` | `WARNING` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Python log level |
| `MCP_LOGGING` | `off` | `off`, `safe`, `full` | MCP transport logging |

**Logging modes:**
- `off`: No MCP logs
- `safe`: Sanitized logs (no sensitive data)
- `full`: Complete protocol logs

## Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_TIMEOUT` | `60` | Request timeout in seconds |
| `APPLY_TIMEOUT` | `60` | Code edit timeout |
| `SEARCH_TIMEOUT` | `60` | Search timeout |

## Advanced

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_BASE_URL` | `https://api.relace.ai` | API endpoint (for self-hosted) |
| `DISABLE_GITIGNORE` | `0` | Ignore `.gitignore` patterns |

## Example Configurations

### Minimal (Quick Start)

```bash
export RELACE_API_KEY="your-key-here"
export MCP_BASE_DIR="/path/to/project"
```

### With Cloud Tools

```bash
export RELACE_API_KEY="your-key-here"
export RELACE_CLOUD_TOOLS="1"
export MCP_SEARCH_RETRIEVAL="1"
```

### Debug Mode

```bash
export RELACE_API_KEY="your-key-here"
export MCP_LOG_LEVEL="DEBUG"
export MCP_LOGGING="safe"
```

### Alternative Provider (OpenAI)

```bash
export OPENAI_API_KEY="your-openai-key"
export APPLY_PROVIDER="openai"
export SEARCH_PROVIDER="openai"
```

## See Also

- [Quick Start](../getting-started/quick-start.md) - Basic setup
- [Configuration](../configuration/overview.md) - MCP client configs
- [Advanced](overview.md) - Advanced usage
