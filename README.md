<p align="right">
  <strong>English</strong> | <a href="README.zh-CN.md">简体中文</a>
</p>

# Unofficial Relace MCP Server

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![100% AI-Generated](https://img.shields.io/badge/100%25%20AI-Generated-ff69b4.svg)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/possible055/relace-mcp/badge)](https://scorecard.dev/viewer/?uri=github.com/possible055/relace-mcp)

> **Unofficial** — Personal project, not affiliated with Relace.
>
> **Built with AI** — Developed entirely with AI assistance (Antigravity, Codex, Cursor, Github Copilot, Windsurf).

MCP server for [Relace](https://www.relace.ai/) — AI-powered instant code merging and agentic codebase search.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [git](https://git-scm.com/) — for `cloud_sync` to respect `.gitignore`
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) — recommended for `fast_search` (falls back to Python regex if unavailable)

### Platform Notes

| Platform | Status | Notes |
|----------|--------|-------|
| Linux | ✅ Fully supported | Primary development platform |
| macOS | ✅ Fully supported | All features available |
| Windows | ⚠️ Partial | `bash` tool unavailable; use WSL for full functionality |

> **Windows users:** The `bash` tool requires a Unix shell. Install [WSL](https://learn.microsoft.com/windows/wsl/install) for full feature parity, or use other exploration tools (`view_file`, `grep_search`, `glob`).

## Quick Start

Get your API key from [Relace Dashboard](https://app.relace.ai/settings/billing), then add to your MCP client:

<details>
<summary><strong>Cursor</strong></summary>

`~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/absolute/path/to/your/project"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Claude Code</strong></summary>

```bash
claude mcp add relace \
  --env RELACE_API_KEY=rlc-your-api-key \
  --env RELACE_BASE_DIR=/absolute/path/to/your/project \
  -- uv tool run relace-mcp
```

</details>

<details>
<summary><strong>Windsurf</strong></summary>

`~/.codeium/windsurf/mcp_config.json`

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "rlc-your-api-key",
        "RELACE_BASE_DIR": "/absolute/path/to/your/project"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>VS Code</strong></summary>

`.vscode/mcp.json`

```json
{
  "mcp": {
    "servers": {
      "relace": {
        "type": "stdio",
        "command": "uv",
        "args": ["tool", "run", "relace-mcp"],
        "env": {
          "RELACE_API_KEY": "rlc-your-api-key",
          "RELACE_BASE_DIR": "${workspaceFolder}"
        }
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Codex CLI</strong></summary>

`~/.codex/config.toml`

```toml
[mcp_servers.relace]
command = "uv"
args = ["tool", "run", "relace-mcp"]

[mcp_servers.relace.env]
RELACE_API_KEY = "rlc-your-api-key"
RELACE_BASE_DIR = "/absolute/path/to/your/project"
```

</details>

> **Note:** `RELACE_BASE_DIR` is optional. If not set, the server auto-detects via MCP Roots or Git. If set, it must be an absolute path.

## Features

- **Fast Apply** — Apply code edits at 10,000+ tokens/sec via Relace API
- **Fast Search** — Agentic codebase exploration with natural language queries
- **Cloud Sync** — Upload local codebase to Relace Cloud for semantic search
- **Cloud Search** — Semantic code search over cloud-synced repositories

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RELACE_API_KEY` | ✅ | API key from [Relace Dashboard](https://app.relace.ai/settings/billing) |
| `RELACE_BASE_DIR` | ❌ | Absolute path to project root (auto-detected via MCP Roots if not set) |
| `RELACE_DEFAULT_ENCODING` | ❌ | Force file encoding (e.g., `gbk`, `big5`) for legacy repos |
| `RELACE_ENCODING_SAMPLE_LIMIT` | ❌ | Max files for auto-detecting encoding (default: `30`) |

> **Note:** When `RELACE_BASE_DIR` is not set, the server automatically detects your project root using:
> 1. MCP Roots (workspace info from your editor)
> 2. Git repository root (if found)
> 3. Current working directory (fallback)
>
> ⚠️ **Warning:** Fallback to CWD/Git can be unstable if MCP Roots fail. Explicit `RELACE_BASE_DIR` is recommended.

> For advanced settings, see [docs/advanced.md](docs/advanced.md).

## Tools

| Tool | Description |
|------|-------------|
| `fast_apply` | Apply code edits at 10,000+ tokens/sec |
| `fast_search` | Agentic codebase search with natural language |
| `cloud_sync` | Upload local codebase to Relace Cloud |
| `cloud_search` | Semantic search over cloud-synced repos |
| `cloud_list` | List cloud repositories |
| `cloud_info` | Get sync status |
| `cloud_clear` | Delete cloud repo and local state |

> For detailed parameters and examples, see [docs/tools.md](docs/tools.md).

## Logging

> **Note:** File logging is opt-in. Enable with `RELACE_LOGGING=1`.

Operation logs are written to a cross-platform state directory:
- **Linux**: `~/.local/state/relace/relace.log`
- **macOS**: `~/Library/Application Support/relace/relace.log`
- **Windows**: `%LOCALAPPDATA%\relace\relace.log`

> For log format and advanced options, see [docs/advanced.md](docs/advanced.md#logging).

## Troubleshooting

Common issues:
- `RELACE_API_KEY is not set`: Set the key in your environment or MCP config.
- `RELACE_BASE_DIR does not exist` / `INVALID_PATH`: Ensure the path exists and is within `RELACE_BASE_DIR`.
- `NEEDS_MORE_CONTEXT` / `APPLY_NOOP`: Include 1–3 real anchor lines before and after the target block.
- `FILE_TOO_LARGE`: File exceeds the 1MB size limit; split large files or increase limit.
- `ENCODING_ERROR`: Cannot detect file encoding; set `RELACE_DEFAULT_ENCODING` explicitly.
- `FILE_NOT_WRITABLE` / `PERMISSION_ERROR`: Check file and directory write permissions.
- `AUTH_ERROR`: Verify your `RELACE_API_KEY` is valid and not expired.
- `RATE_LIMIT`: Too many requests; wait and retry later.
- `TIMEOUT_ERROR` / `NETWORK_ERROR`: Check network connectivity; increase timeout via `RELACE_TIMEOUT_SECONDS`.

> **Windows users:** The `bash` tool in `fast_search` is unavailable on Windows. Use WSL or rely on other exploration tools.

## Development

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync
uv run pytest
```
