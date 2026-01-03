# Advanced Usage

This document covers advanced configuration options for power users and developers.

## Table of Contents

- [Environment Variables Reference](#environment-variables-reference)
- [Sync Modes](#sync-modes)
- [Logging](#logging)
- [Alternative Providers](#alternative-providers)
- [Remote Deployment](#remote-deployment-streamable-http)

---

## Environment Variables Reference

All environment variables can be set in your shell or in the `env` section of your MCP configuration.

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_API_KEY` | — | **Required.** Your Relace API key |
| `RELACE_BASE_DIR` | cwd | Restrict file access to this directory |
| `RELACE_DEFAULT_ENCODING` | — | Force default encoding for project files (e.g., `gbk`, `big5`) |
| `RELACE_LOGGING` | `0` | Set to `1` to enable file logging |

### Fast Apply

| Variable | Default | Description |
|----------|---------|-------------|
| `APPLY_PROVIDER` | `relace` | Provider: `relace`, `openai`, `openrouter`, `cerebras`, etc. |
| `APPLY_ENDPOINT` | (Relace official) | Override base URL |
| `APPLY_MODEL` | `auto` | Override model name |
| `APPLY_API_KEY` | — | API key for non-Relace providers |
| `APPLY_PROMPT_FILE` | — | Override apply prompt YAML path |
| `APPLY_TIMEOUT_SECONDS` | `60` | Request timeout |
| `APPLY_POST_CHECK` | `0` | Post-merge validation (may increase failures) |

> **Note:** `RELACE_APPLY_*`, `RELACE_TIMEOUT_SECONDS`, `RELACE_EXPERIMENTAL_POST_CHECK` variants are deprecated but still supported with warnings.

### Fast Search

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_PROVIDER` | `relace` | Provider: `relace`, `openai`, `openrouter`, `cerebras`, etc. |
| `SEARCH_ENDPOINT` | (Relace official) | Override base URL |
| `SEARCH_MODEL` | `relace-search` | Override model name |
| `SEARCH_API_KEY` | — | API key for non-Relace providers |
| `SEARCH_PROMPT_FILE` | — | Override search prompt YAML path |
| `SEARCH_TIMEOUT_SECONDS` | `120` | Request timeout |
| `SEARCH_MAX_TURNS` | `6` | Maximum agent loop turns |
| `SEARCH_ENABLED_TOOLS` | `view_file,view_directory,grep_search,glob,find_symbol` | Tool allowlist (comma-separated) |
| `SEARCH_PARALLEL_TOOL_CALLS` | `1` | Enable parallel tool calls |
| `SEARCH_TOOL_STRICT` | `1` | Include `strict` field in tool schemas |
| `SEARCH_LSP_TIMEOUT_SECONDS` | `15.0` | LSP startup/request timeout |

> **Note:** `RELACE_SEARCH_*`, `RELACE_LSP_TIMEOUT_SECONDS` variants are deprecated but still supported with warnings.

### Cloud Sync

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` | API endpoint for cloud operations |
| `RELACE_REPO_ID` | — | Pre-configured repo UUID (skip list/create) |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` | Sync operation timeout |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` | Maximum files per sync |
| `RELACE_REPO_LIST_MAX` | `10000` | Maximum repos to fetch |
| `RELACE_UPLOAD_MAX_WORKERS` | `8` | Concurrent upload workers |

### Third-Party API Keys

When using alternative providers, set the corresponding API key:

| Variable | Used When |
|----------|-----------|
| `OPENAI_API_KEY` | `*_PROVIDER=openai` and no `*_API_KEY` set |
| `OPENROUTER_API_KEY` | `*_PROVIDER=openrouter` and no `*_API_KEY` set |
| `CEREBRAS_API_KEY` | `*_PROVIDER=cerebras` and no `*_API_KEY` set |

### Experimental

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_EXPERIMENTAL_LOGGING` | — | Deprecated alias for `RELACE_LOGGING` |

> **Note:** `RELACE_EXPERIMENTAL_POST_CHECK` has been renamed to `APPLY_POST_CHECK` and moved to Fast Apply section.

---

## Sync Modes

The `cloud_sync` tool supports three sync modes:

| Mode | Trigger | Description |
|------|---------|-------------|
| Incremental | (default) | Only uploads new/modified files, deletes removed files |
| Safe Full | `force=True`, first sync, or HEAD changed | Uploads all files; suppresses deletes unless HEAD changed |
| Mirror Full | `force=True, mirror=True` | Completely overwrites cloud to match local |

When git HEAD changes since last sync (e.g., branch switch, rebase), Safe Full mode automatically cleans up zombie files from the old ref.

---

## Logging

File logging is opt-in. Enable with `RELACE_LOGGING=1`.

### Log Location

| Platform | Path |
|----------|------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

### Log Format

Logs are written in JSON Lines (JSONL) format:

```json
{"kind":"apply_success","level":"info","trace_id":"a1b2c3d4","latency_ms":150,"file_path":"/path/to/file.py",...}
```

### Event Types

| Event Kind | Description |
|------------|-------------|
| `create_success` | New file created |
| `apply_success` | Edit applied successfully |
| `apply_error` | Edit failed |
| `search_start` | Search started |
| `search_turn` | Agent loop turn state |
| `tool_call` | Tool call with timing |
| `search_complete` | Search completed |
| `search_error` | Search failed |

### Log Rotation

- Rotates automatically at **10 MB**
- Keeps up to **5** rotated files
- Naming: `relace.YYYYMMDD_HHMMSS.log`

---

## Alternative Providers

Both `fast_apply` and `fast_search` can use OpenAI-compatible providers instead of Relace.

### Configuration Pattern

```bash
# For fast_apply
export APPLY_PROVIDER=openrouter
export APPLY_API_KEY=sk-or-v1-xxx
export APPLY_MODEL=anthropic/claude-3.5-sonnet

# For fast_search
export SEARCH_PROVIDER=openai
export SEARCH_API_KEY=sk-xxx
export SEARCH_MODEL=gpt-4o
```

### API Key Resolution

1. `APPLY_API_KEY` / `SEARCH_API_KEY` (explicit)
2. Provider-specific key (e.g., `OPENROUTER_API_KEY`)
3. `RELACE_API_KEY` (only for `relace` provider)

### LSP Tool

The `find_symbol` tool uses Language Server Protocol for Python semantic queries:
- `definition`: Jump to symbol definition
- `references`: Find all symbol references

> **Note:** Uses `basedpyright` (bundled). First call incurs 2-5s startup latency.

### OpenAI Structured Outputs

When using OpenAI providers with `SEARCH_TOOL_STRICT=1` (default), parallel tool calls are automatically disabled. To enable parallel calls:

```bash
export SEARCH_TOOL_STRICT=0
export SEARCH_PARALLEL_TOOL_CALLS=1
```

### Bash Tool

The `bash` tool is disabled by default. To enable on Unix:

```json
{
  "mcpServers": {
    "relace": {
      "env": {
        "SEARCH_ENABLED_TOOLS": "view_file,view_directory,grep_search,glob,find_symbol,bash"
      }
    }
  }
}
```

---

## Remote Deployment (Streamable HTTP)

> **Security:** This server can read/write files. Do **NOT** expose directly to the internet. Use `stdio`, or put HTTP behind authentication/VPN.

### Running the Server

```bash
relace-mcp -t streamable-http --host 0.0.0.0 -p 8000
```

### Client Configuration

```json
{
  "mcpServers": {
    "relace": {
      "type": "streamable-http",
      "url": "http://your-server:8000/mcp"
    }
  }
}
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port`, `-p` | `8000` | Port number |
| `--path` | `/mcp` | URL path for MCP endpoint |
