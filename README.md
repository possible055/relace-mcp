<p align="right">
  <strong>English</strong> | <a href="README.zh-CN.md">简体中文</a>
</p>

# Unofficial Relace MCP Server

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg?style=flat-square)](https://pypi.org/project/relace-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
![100% AI-Generated](https://img.shields.io/badge/100%25%20AI-Generated-ff69b4.svg?style=flat-square)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/possible055/relace-mcp?style=flat-square)](https://scorecard.dev/viewer/?uri=github.com/possible055/relace-mcp)

> **Unofficial** — Personal project, not affiliated with Relace.
>
> **Built with AI** — Developed entirely with AI assistance (Antigravity, Codex, Cursor, Github Copilot, Windsurf).

MCP server providing AI-powered code editing and intelligent codebase exploration tools.

| Without | With `agentic_search` + `fast_apply` |
|:--------|:-------------------------------------|
| Manual grep, misses related files | Ask naturally, get precise locations |
| Edits break imports elsewhere | Traces imports and call chains |
| Full rewrites burn tokens | Describe changes, no line numbers |
| Line number errors corrupt code | 10,000+ tokens/sec merging |

## Features

- **Fast Apply** — Apply code edits at 10,000+ tokens/sec via Relace API
- **Agentic Search** — Agentic codebase exploration with natural language queries
- **Agentic Retrieval** — Hybrid semantic hints + live code exploration, with stale-hint support and explicit cloud maintenance (enable with `MCP_SEARCH_RETRIEVAL=1`; choose the backend with `MCP_RETRIEVAL_BACKEND`)
- **Cloud Search** — Semantic code search over cloud-synced repositories

## Quick Start

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [git](https://git-scm.com/), [ripgrep](https://github.com/BurntSushi/ripgrep) (recommended)

Using Relace (default) or `RELACE_CLOUD_TOOLS=1`: get your API key from [Relace Dashboard](https://app.relace.ai/settings/billing), then add to your MCP client:

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
        "MCP_BASE_DIR": "/absolute/path/to/your/project"
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
  --env MCP_BASE_DIR=/absolute/path/to/your/project \
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
        "MCP_BASE_DIR": "/absolute/path/to/your/project"
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
          "MCP_BASE_DIR": "${workspaceFolder}"
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
MCP_BASE_DIR = "/absolute/path/to/your/project"
```

</details>

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `RELACE_API_KEY` | ✅* | API key from [Relace Dashboard](https://app.relace.ai/settings/billing); required for Relace providers and cloud tools |
| `RELACE_CLOUD_TOOLS` | ❌ | Set to `1` to enable cloud tools |
| `MCP_SEARCH_RETRIEVAL` | ❌ | Set to `1` to register the `agentic_retrieval` tool |
| `MCP_RETRIEVAL_BACKEND` | ❌ | Semantic retrieval backend: `relace` (default), `codanna`, `chunkhound`, `auto`, or `none` |
| `MCP_RETRIEVAL_HINT_POLICY` | ❌ | Retrieval hint policy: `prefer-stale` (default) or `strict` |
| `SEARCH_BASH_TOOLS` | ❌ | Bash tool toggle: `1` (on), `0` (off, default) |
| `SEARCH_LSP_TOOLS` | ❌ | LSP tools toggle: `1` (on), `0` (off, default) |
| `MCP_BASE_DIR` | ❌ | Project root override (auto-detected via MCP Roots → Git → workspace storage → CWD) |
| `MCP_LOGGING` | ❌ | File logging: `off` (default), `safe`, `full` |
| `MCP_DOTENV_PATH` | ❌ | Path to `.env` file for centralized config |

`*` Optional if **both**: (1) `APPLY_PROVIDER` and `SEARCH_PROVIDER` are non-Relace providers, and (2) `RELACE_CLOUD_TOOLS=false`.

For `.env` usage, encoding settings, custom LLM providers, and more, see [docs/advanced.md](docs/advanced.md).

## Tools

Always-available tools: `fast_apply`, `agentic_search`, `index_status`. Cloud tools require `RELACE_CLOUD_TOOLS=1`. `agentic_retrieval` requires `MCP_SEARCH_RETRIEVAL=1`, and its semantic backend is selected via `MCP_RETRIEVAL_BACKEND`.

`agentic_retrieval` can use stale semantic hints and then verify them against live code. It does not run `cloud_sync` implicitly; use `cloud_sync` as the explicit maintenance tool when you want to refresh the cloud index ahead of retrieval.

Live local exploration keeps `.gitignore` filtering in place, and exact-text probes automatically use a faster literal search path when regex features are unnecessary.

For detailed parameters, see [docs/tools.md](docs/tools.md).

## Language Support

LSP tools use external language servers installed on your system.

| Language | Language Server | Install Command |
|----------|-----------------|-----------------|
| Python | basedpyright | (bundled) |
| TypeScript/JS | typescript-language-server | `npm i -g typescript-language-server typescript` |
| Go | gopls | `go install golang.org/x/tools/gopls@latest` |
| Rust | rust-analyzer | `rustup component add rust-analyzer` |

## Dashboard

Real-time terminal UI for monitoring operations.

```bash
pip install relace-mcp[tools]
relogs
```

For detailed usage, see [docs/dashboard.md](docs/dashboard.md).

## Benchmark

Evaluate `agentic_search` performance using the [Loc-Bench](https://huggingface.co/datasets/IvanaXu/LocAgent) code localization dataset.

```bash
# Install benchmark dependencies
pip install relace-mcp[benchmark]

# Build dataset from Hugging Face
uv run python -m benchmark.cli.build_locbench --output artifacts/data/raw/locbench_v1.jsonl

# Run evaluation
uv run python -m benchmark.cli.run --dataset artifacts/data/raw/locbench_v1.jsonl --limit 20
```

For grid search, analysis tools, and metrics interpretation, see [docs/benchmark.md](docs/benchmark.md).

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Linux | ✅ Fully supported | Primary development platform |
| macOS | ✅ Fully supported | All features available |
| Windows | ⚠️ Partial | `bash` tool unavailable; use WSL for full functionality |

## Troubleshooting

| Error | Solution |
|-------|----------|
| `RELACE_API_KEY is not set` | Set the key in your environment or MCP config |
| `NEEDS_MORE_CONTEXT` | Include 1–3 anchor lines before/after target block |
| `FILE_TOO_LARGE` | File exceeds 10MB; split file |
| `ENCODING_ERROR` | Set `RELACE_DEFAULT_ENCODING` explicitly |
| `AUTH_ERROR` | Verify API key is valid and not expired |
| `RATE_LIMIT` | Too many requests; wait and retry |
| `CONNECTION_TIMEOUT` | Check network connection or increase timeout setting |
| `INVALID_PATH` | File path doesn't exist or no permission; verify path and access rights |
| `SYNTAX_ERROR` | Invalid edit_snippet format; ensure placeholder syntax is correct |
| `NO_MATCH_FOUND` | No search results; try broader query or run `cloud_sync` first |
| `CLOUD_NOT_SYNCED` | Repository not synced to Relace Cloud; run `cloud_sync` first |
| `CONFLICT_DETECTED` | Edit conflict; file was modified, re-read before editing |

## Development

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync --extra dev --extra benchmark
uv run pytest
uv run --extra dev --extra benchmark pytest benchmark/tests -q
```

## License

MIT
