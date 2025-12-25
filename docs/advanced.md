# Advanced Usage

This document covers advanced configuration options for power users and developers.

## Table of Contents

- [Sync Modes](#sync-modes)
- [Developer Overrides](#developer-overrides)
- [Encoding](#encoding)
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
| `RELACE_SEARCH_ENDPOINT` | `https://search.endpoint.relace.run/v1/search` |
| `RELACE_SEARCH_MODEL` | `relace-search` |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `120` |
| `RELACE_SEARCH_MAX_TURNS` | `6` |
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` |
| `RELACE_REPO_ID` | — (pre-configured repo UUID to skip list/create) |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` |

---

## Encoding

Relace MCP aims to work with legacy-encoded repos (e.g., GBK/Big5) without crashing tools like `fast_apply`, `view_file`, `grep_search`, and `cloud_sync`.

**Recommended best practice:** convert the repo to UTF-8 (and keep it consistent). If you must keep legacy encodings:

- For Python source, add a PEP 263 coding cookie on the first or second line (e.g., `# -*- coding: gbk -*-`).
- If your repo is predominantly a single legacy encoding, set `RELACE_DEFAULT_ENCODING` explicitly.

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_DEFAULT_ENCODING` | — | Force the default encoding used when reading/writing project files (e.g., `gbk`, `big5`) |
| `RELACE_ENCODING_SAMPLE_LIMIT` | `30` | Max files sampled at startup for auto-detecting a dominant project encoding |

---

## Fast Apply Provider Swap

Switch to OpenAI-compatible providers for `fast_apply`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_APPLY_PROVIDER` | `relace` | Provider label. `relace` uses `RELACE_API_KEY`; other values use the provider's API key. |
| `RELACE_APPLY_ENDPOINT` | — | Optional override base URL (SDK posts to `/chat/completions`; trailing `/chat/completions` is auto-stripped). |
| `RELACE_APPLY_MODEL` | — | Optional override model |
| `RELACE_APPLY_API_KEY` | — | Optional direct API key override (recommended for non-Relace providers) |
| `RELACE_APPLY_API_KEY_ENV` | — | Optional: env var name holding the API key |
| `RELACE_APPLY_HEADERS` | — | Optional JSON object for default headers (e.g. `{\"HTTP-Referer\":\"...\",\"X-Title\":\"...\"}`) |
| `OPENAI_API_KEY` | — | Used when `RELACE_APPLY_PROVIDER=openai` and no `RELACE_APPLY_API_KEY*` is set |
| `OPENROUTER_API_KEY` | — | Used when `RELACE_APPLY_PROVIDER=openrouter` and no `RELACE_APPLY_API_KEY*` is set |
| `CEREBRAS_API_KEY` | — | Used when `RELACE_APPLY_PROVIDER=cerebras` and no `RELACE_APPLY_API_KEY*` is set |

---

## Fast Search Provider Swap

Switch to OpenAI-compatible providers for `fast_search`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_SEARCH_PROVIDER` | `relace` | Provider label. `relace` uses `RELACE_API_KEY`; other values use the provider's API key. |
| `RELACE_SEARCH_ENDPOINT` | — | Optional override base URL (SDK posts to `/chat/completions`; trailing `/chat/completions` is auto-stripped). |
| `RELACE_SEARCH_MODEL` | — | Optional override model |
| `RELACE_SEARCH_API_KEY` | — | Optional direct API key override (recommended for non-Relace providers) |
| `RELACE_SEARCH_API_KEY_ENV` | — | Optional: env var name holding the API key |
| `RELACE_SEARCH_HEADERS` | — | Optional JSON object for default headers (e.g. `{\"HTTP-Referer\":\"...\",\"X-Title\":\"...\"}`) |
| `RELACE_SEARCH_API_COMPAT` | — | Optional: force request schema (`openai` or `relace`) |
| `RELACE_SEARCH_TOOL_STRICT` | `1` | Set to `0` to omit the non-standard `strict` field from tool schemas |
| `OPENAI_API_KEY` | — | Used when `RELACE_SEARCH_PROVIDER=openai` and no `RELACE_SEARCH_API_KEY*` is set |
| `OPENROUTER_API_KEY` | — | Used when `RELACE_SEARCH_PROVIDER=openrouter` and no `RELACE_SEARCH_API_KEY*` is set |
| `CEREBRAS_API_KEY` | — | Used when `RELACE_SEARCH_PROVIDER=cerebras` and no `RELACE_SEARCH_API_KEY*` is set |

---

## Fast Search Tool Control

| Variable | Default | Description |
|----------|---------|-------------|
| `RELACE_SEARCH_ENABLED_TOOLS` | — | Comma-separated allowlist (`view_file`, `view_directory`, `grep_search`, `glob`, `bash`). `report_back` is always enabled. |
| `RELACE_SEARCH_PARALLEL_TOOL_CALLS` | `1` | Enable parallel tool calls for lower latency |

### OpenAI Structured Outputs Compatibility

When using OpenAI or OpenAI-compatible providers (not `relace`) with `RELACE_SEARCH_TOOL_STRICT=1` (default), `parallel_tool_calls` is automatically disabled to comply with [OpenAI's Structured Outputs limitations](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs).

To use parallel tool calls with OpenAI providers, disable strict mode:

```bash
export RELACE_SEARCH_TOOL_STRICT=0
export RELACE_SEARCH_PARALLEL_TOOL_CALLS=1
```

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
