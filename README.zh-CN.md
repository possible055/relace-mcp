<p align="right">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

# Unofficial Relace MCP 服务器

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg?style=flat-square)](https://pypi.org/project/relace-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
![100% AI生成](https://img.shields.io/badge/100%25%20AI-Generated-ff69b4.svg?style=flat-square)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/possible055/relace-mcp?style=flat-square)](https://scorecard.dev/viewer/?uri=github.com/possible055/relace-mcp)

> **非官方** — 个人项目，与 Relace 无关联。
>
> **AI 构建** — 完全由 AI 辅助开发（Antigravity、Codex、Cursor、Github Copilot、Windsurf）。

提供 AI 驱动代码编辑和智能代码库探索工具的 MCP 服务器。

| Without | With `agentic_search` + `fast_apply` |
|:--------|:-------------------------------------|
| 手动 grep，漏掉相关文件 | 自然提问，精确定位 |
| 改一处破坏其他导入 | 追踪导入和调用链 |
| 完整重写浪费 tokens | 描述变更，无需行号 |
| 行号错误破坏代码 | 10,000+ tokens/秒 合并 |

## 功能特性

- **快速应用** — 通过 Relace API 以 10,000+ tokens/秒的速度应用代码编辑
- **智能搜索** — 使用自然语言查询进行智能代码库探索
- **智能检索** — 结合语义 hints 与 live code exploration 的混合检索，支持 stale hints，并将 cloud maintenance 保持为显式操作（使用 `MCP_SEARCH_RETRIEVAL=1` 启用，backend 由 `MCP_RETRIEVAL_BACKEND` 选择）
- **云端搜索** — 对云端同步的仓库进行语义代码搜索

## 快速开始

**前置需求：** [uv](https://docs.astral.sh/uv/)、[git](https://git-scm.com/)、[ripgrep](https://github.com/BurntSushi/ripgrep)（推荐）

使用 Relace（默认）或 `RELACE_CLOUD_TOOLS=1`：从 [Relace Dashboard](https://app.relace.ai/settings/billing) 获取 API 密钥，然后添加到你的 MCP 客户端：

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

## 配置

| 变量 | 必需 | 说明 |
|------|------|------|
| `RELACE_API_KEY` | ✅* | 来自 [Relace Dashboard](https://app.relace.ai/settings/billing) 的 API 密钥；在使用 Relace provider 或云端工具时必需 |
| `RELACE_CLOUD_TOOLS` | ❌ | 设为 `1` 启用云端工具 |
| `MCP_SEARCH_RETRIEVAL` | ❌ | 设为 `1` 注册 `agentic_retrieval` 工具 |
| `MCP_RETRIEVAL_BACKEND` | ❌ | semantic retrieval backend：`relace`（默认）、`codanna`、`chunkhound`、`auto` 或 `none` |
| `MCP_RETRIEVAL_HINT_POLICY` | ❌ | retrieval hint policy：`prefer-stale`（默认）或 `strict` |
| `MCP_BACKGROUND_INDEX_MONITOR` | ❌ | 为 local index 启用可选的周期 refresh monitor；要求固定的 `MCP_BASE_DIR` 与 local backend |
| `MCP_BACKGROUND_INDEX_INTERVAL_SECONDS` | ❌ | 周期 local index monitor 的检查间隔（秒，默认 `300`） |
| `MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS` | ❌ | 首次周期 local index 检查前的初始延迟（秒，默认 `30`） |
| `SEARCH_BASH_TOOLS` | ❌ | 启用 `agentic_search` / `agentic_retrieval` 内部使用的 `bash` subtool：`1`（开）、`0`（关，默认） |
| `SEARCH_LSP_TOOLS` | ❌ | 启用 `agentic_search` / `agentic_retrieval` 内部使用的 `find_symbol` / `search_symbol` subtools：`1`（开）、`0`（关，默认） |
| `MCP_BASE_DIR` | ❌ | 项目根目录覆盖值（自动检测顺序：MCP Roots → Git → workspace storage → CWD） |
| `MCP_LOGGING` | ❌ | 文件日志：`off`（默认）、`safe`、`full` |
| `MCP_DOTENV_PATH` | ❌ | `.env` 文件路径，用于集中配置 |

`*` 仅当**同时满足**：(1) `APPLY_PROVIDER` 与 `SEARCH_PROVIDER` 均为非 Relace 提供商，且 (2) `RELACE_CLOUD_TOOLS=false` 时可省略。

`.env` 使用方法、编码设置、自定义 LLM 等进阶设置，请参见 [docs/advanced.zh-CN.md](docs/advanced.zh-CN.md)。

## 工具

始终可用的 top-level tools 有：`fast_apply`、`agentic_search`。`index_status` 只会在 `RELACE_CLOUD_TOOLS=1`，或 `PATH` 中可找到本地 index CLI（`codanna` / `chunkhound`）时暴露。云端工具需设置 `RELACE_CLOUD_TOOLS=1`。`agentic_retrieval` 需设置 `MCP_SEARCH_RETRIEVAL=1`，其 semantic backend 由 `MCP_RETRIEVAL_BACKEND` 选择。

可用性发现请使用 MCP 原生接口：tools 用 `list_tools()`，resources 用 `list_resources()`。

`index_status` 现在还会返回 `background_monitor` 摘要，用于显示可选的 local index monitor 是否处于活动状态。这个 monitor 只面向单进程、固定 `MCP_BASE_DIR` 的部署；如果你使用 multi-worker 或 multi-pod HTTP 部署，建议关闭它，改用 backend 自带的 watch/daemon 或外部 scheduler。

`SEARCH_BASH_TOOLS` 与 `SEARCH_LSP_TOOLS` 不会给 `list_tools()` 新增 top-level 条目。它们只会扩展 `agentic_search` / `agentic_retrieval` 在探索代码库时可使用的内部工具集。

`agentic_retrieval` 可以先使用 stale semantic hints，再回到 live code 做确认；它不会隐式执行 `cloud_sync`。如果你要主动刷新 cloud index，请显式调用 `cloud_sync`。

本地 live exploration 会持续保留 `.gitignore` 过滤；当查询不需要 regex 特性时，exact-text probes 会自动走更快的 literal search path。

详细参数请参见 [docs/tools.zh-CN.md](docs/tools.zh-CN.md)。

## 语言支持

LSP 工具使用系统上安装的外部语言服务器。

| 语言 | 语言服务器 | 安装命令 |
|------|-----------|----------|
| Python | basedpyright | (已内置) |
| TypeScript/JS | typescript-language-server | `npm i -g typescript-language-server typescript` |
| Go | gopls | `go install golang.org/x/tools/gopls@latest` |
| Rust | rust-analyzer | `rustup component add rust-analyzer` |

## 仪表盘

实时终端 UI，用于监控操作。

```bash
pip install relace-mcp[tools]
relogs
```

详细用法请参见 [docs/dashboard.zh-CN.md](docs/dashboard.zh-CN.md)。

## 基准测试

使用 [Loc-Bench](https://huggingface.co/datasets/IvanaXu/LocAgent) 代码定位数据集评估 `agentic_search` 性能。

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync --extra benchmark

# 从 Hugging Face 构建数据集
uv run --extra benchmark python -m benchmark.cli.build_locbench --output artifacts/data/raw/locbench_v1.jsonl

# 运行评估
uv run --extra benchmark python -m benchmark.cli.run --dataset artifacts/data/raw/locbench_v1.jsonl --limit 20
```

所有 benchmark 产物都会写入 `benchmark/.data/`。

网格搜索、分析工具及指标说明请参见 [docs/benchmark.zh-CN.md](docs/benchmark.zh-CN.md)。

## 平台支持

| 平台 | 状态 | 备注 |
|------|------|------|
| Linux | ✅ 完全支持 | 主要开发平台 |
| macOS | ✅ 完全支持 | 所有功能可用 |
| Windows | ⚠️ 部分支持 | `bash` 工具不可用；使用 WSL 以获得完整功能 |

## 故障排除

| 错误或提示信息 | 解决方案 |
|----------------|----------|
| `RELACE_API_KEY is required ...` | 使用 Relace provider 或云端工具时设置 `RELACE_API_KEY` |
| `NEEDS_MORE_CONTEXT` | 在目标代码块附近提供 1-3 行唯一锚点行 |
| `INVALID_PATH` | 确认路径存在，且位于 `MCP_BASE_DIR` 或允许的额外路径内 |
| `FILE_TOO_LARGE` | 文件超过 10MB；将改动拆成更小的文件或更局部的编辑 |
| `ENCODING_ERROR` | 对非 UTF-8 项目显式设置 `RELACE_DEFAULT_ENCODING` |
| `AUTH_ERROR` | 检查 API key 与 provider 配置 |
| `RATE_LIMIT` | 稍后重试，或降低请求频率 |
| `NETWORK_ERROR` / `TIMEOUT_ERROR` | 检查网络连通性后重试 |
| `APPLY_NOOP` | 增加更具体的锚点或明确新增行，让 merge 能生成 diff |
| `MARKER_LEAKAGE` | 确保占位 marker 仅作为占位符使用，而不是期望写入文件的字面文本 |
| `TRUNCATION_DETECTED` | 将大规模删除拆小，或使用显式 remove directives |
| `BLAST_RADIUS_EXCEEDED` | 将改动拆成更小、更局部的 edits |

## 开发

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync --extra dev --extra benchmark
uv run pytest
uv run --extra dev --extra benchmark pytest benchmark/tests -q
```

## 许可证

MIT
