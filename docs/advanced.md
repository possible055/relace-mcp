# Advanced Usage

This document covers advanced configuration options for power users and developers.

## Table of Contents

- [Sync Modes](#sync-modes)
- [Developer Overrides](#developer-overrides)
- [Fast Apply Provider Swap](#fast-apply-provider-swap)
- [Fast Search Provider Swap](#fast-search-provider-swap)
- [Fast Search Tool Control](#fast-search-tool-control)
- [Remote Deployment](#remote-deployment-streamable-http)

---

## Sync Modes

The `cloud_sync` tool supports three sync modes:

| Mode | Trigger | Description |
|------|---------|-------------|
| Incremental | (default) | Only uploads new/modified files, deletes removed files |
| Safe Full | `force=True`, first sync, or HEAD changed | Uploads all files; suppresses deletes unless HEAD changed |
| Mirror Full | `force=True, mirror=True` | Completely overwrites cloud to match local |

### HEAD Change Detection

When git HEAD changes since last sync (e.g., branch switch, rebase, commit amend), Safe Full mode automatically cleans up zombie files from the old ref to prevent stale search results.

---

## Developer Overrides

These settings allow temporary overrides when the official API updates before the package catches up:

| Variable | Default |
|----------|---------|
| `RELACE_APPLY_ENDPOINT` | `https://instantapply.endpoint.relace.run/v1/apply` |
| `RELACE_APPLY_MODEL` | `auto` |
| `RELACE_TIMEOUT_SECONDS` | `60` |
| `RELACE_MAX_RETRIES` | `3` |
| `RELACE_RETRY_BASE_DELAY` | `1.0` |
| `RELACE_SEARCH_ENDPOINT` | `https://search.endpoint.relace.run/v1/search/chat/completions` |
| `RELACE_SEARCH_MODEL` | `relace-search` |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `120` |
| `RELACE_SEARCH_MAX_TURNS` | `6` |
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` |
| `RELACE_REPO_ID` | — (pre-configured repo UUID to skip list/create) |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` |

---

## Fast Apply Provider Swap

Switch to OpenAI-compatible providers for `fast_apply`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_APPLY_PROVIDER` | `relace` | Set to `openai` for OpenAI-compatible mode |
| `RELACE_APPLY_ENDPOINT` | — | Optional override base URL (posts to `/chat/completions`) |
| `RELACE_APPLY_MODEL` | — | Optional override model |
| `OPENAI_API_KEY` | — | Required when `RELACE_APPLY_PROVIDER=openai` |

---

## Fast Search Provider Swap

Switch to OpenAI-compatible providers for `fast_search`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_SEARCH_PROVIDER` | `relace` | Set to `openai` for OpenAI-compatible mode |
| `OPENAI_API_KEY` | — | Required when `RELACE_SEARCH_PROVIDER=openai` |

---

## Fast Search Tool Control

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_SEARCH_ENABLED_TOOLS` | — | Comma-separated allowlist (`view_file`, `view_directory`, `grep_search`, `glob`, `bash`). `report_back` is always enabled. |
| `RELACE_SEARCH_PARALLEL_TOOL_CALLS` | `1` | Enable parallel tool calls for lower latency |

---

## Remote Deployment (Streamable HTTP)

For remote deployment, run with streamable-http transport:

```bash
relace-mcp -t streamable-http -p 8000
```

Connect via:

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

### Additional CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port`, `-p` | `8000` | Port number |
| `--path` | `/mcp` | URL path for MCP endpoint |
