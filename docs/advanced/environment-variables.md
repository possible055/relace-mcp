# Environment Variables

Complete reference for Relace MCP configuration via environment variables.

!!! note "Where to set"
    You can set these in your shell, or in the `env` section of your MCP client configuration.

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_API_KEY` | — | Relace API key from [Dashboard](https://app.relace.ai/settings/billing). Required for Relace provider and for cloud tools. |
| `MCP_BASE_DIR` | — | Restrict file operations to this directory. If unset, the server resolves the base dir from MCP Roots at runtime. |
| `MCP_DOTENV_PATH` | — | Path to a `.env` file to load at startup. If unset, default dotenv search is used. |
| `RELACE_DEFAULT_ENCODING` | — | Force default encoding for project files (e.g., `gbk`, `big5`). If unset, encoding is auto-detected. |

> **Note:** `RELACE_API_KEY` can be omitted if **both**: (1) you use non-Relace providers for `APPLY_PROVIDER` and `SEARCH_PROVIDER`, and (2) `RELACE_CLOUD_TOOLS=0`.

## Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_CLOUD_TOOLS` | `0` | Enable cloud tools (`cloud_sync`, `cloud_search`, `cloud_info`, `cloud_list`, `cloud_clear`). |
| `MCP_SEARCH_RETRIEVAL` | `0` | Enable the `agentic_retrieval` tool. |
| `MCP_RETRIEVAL_BACKEND` | `relace` | Retrieval backend for `agentic_retrieval`: `relace`, `codanna`, `chunkhound`, or `none` (disable semantic hints). |

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_LOG_LEVEL` | `WARNING` | Python log level for stderr logging (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `MCP_LOGGING` | `off` | Local JSONL file logging: `off`, `safe` (redacted), or `full` (no redaction). |

## Fast Apply

| Variable | Default | Description |
|----------|---------|-------------|
| `APPLY_PROVIDER` | `relace` | Provider identifier (`relace`, `openai`, `openrouter`, `cerebras`, …). |
| `APPLY_ENDPOINT` | (Relace official) | Override base URL (OpenAI-compatible). |
| `APPLY_MODEL` | `auto` | Override model name. |
| `APPLY_API_KEY` | — | API key for non-Relace providers (overrides derived keys). |
| `APPLY_PROMPT_FILE` | — | Override apply prompt YAML path. |
| `APPLY_TIMEOUT_SECONDS` | `60` | Request timeout in seconds. |
| `APPLY_TEMPERATURE` | `0.0` | Sampling temperature (0.0–2.0). |
| `APPLY_SEMANTIC_CHECK` | `0` | Post-merge semantic validation (may increase failures). |

## Agentic Search

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_PROVIDER` | `relace` | Provider identifier (`relace`, `openai`, `openrouter`, `cerebras`, …). |
| `SEARCH_ENDPOINT` | (Relace official) | Override base URL (OpenAI-compatible). |
| `SEARCH_MODEL` | `relace-search` | Override model name. |
| `SEARCH_API_KEY` | — | API key for non-Relace providers (overrides derived keys). |
| `SEARCH_PROMPT_FILE` | — | Override search prompt YAML path. |
| `SEARCH_TIMEOUT_SECONDS` | `120` | Request timeout (also used as `agentic_search` wall-clock budget). |
| `SEARCH_TEMPERATURE` | `1.0` | Sampling temperature (0.0–2.0). |
| `SEARCH_TOP_P` | — | Optional top_p sampling (set only when required by your provider). |
| `SEARCH_MAX_TURNS` | `6` | Maximum agent loop turns. |
| `SEARCH_PARALLEL_TOOL_CALLS` | `1` | Enable parallel tool calls. |
| `SEARCH_TOOL_STRICT` | `1` | Include the non-standard `strict` field in tool schemas (disable with `0` for providers that reject it). |
| `SEARCH_ENABLED_TOOLS` | (basic only) | Tool allowlist (comma/space-separated). `bash` requires explicit opt-in. |
| `SEARCH_LSP_TOOLS` | `false` | LSP tools mode: `false`, `true`, or `auto`. |
| `SEARCH_LSP_TIMEOUT_SECONDS` | `15.0` | LSP startup/request timeout. |
| `SEARCH_LSP_MAX_CLIENTS` | `2` | Maximum concurrent LSP clients. |

## Cloud Tools

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` | API endpoint for cloud operations. |
| `RELACE_REPO_ID` | — | Pre-configured repo UUID (skip list/create). |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` | Sync operation timeout. |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` | Maximum files per sync. |
| `RELACE_REPO_LIST_MAX` | `10000` | Maximum repos to fetch. |
| `RELACE_UPLOAD_MAX_WORKERS` | `8` | Concurrent upload workers. |
| `RELACE_AGENTIC_AUTO_SYNC` | `1` | Auto-sync before `agentic_retrieval` (when cloud tools enabled). |

## Provider API Keys

When using non-Relace providers, you can set provider-specific API keys:

| Variable | Used When |
|----------|-----------|
| `OPENAI_API_KEY` | `*_PROVIDER=openai` and no `*_API_KEY` set |
| `OPENROUTER_API_KEY` | `*_PROVIDER=openrouter` and no `*_API_KEY` set |
| `CEREBRAS_API_KEY` | `*_PROVIDER=cerebras` and no `*_API_KEY` set |

## See Also

- [Advanced Usage](overview.md) - Advanced topics
- [Tool Reference](../tools/reference.md) - Tool schemas and return shapes
