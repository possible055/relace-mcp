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

| Without | With `fast_search` + `fast_apply` |
|:--------|:----------------------------------|
| 手动 grep，漏掉相关文件 | 自然提问，精确定位 |
| 改一处破坏其他导入 | 追踪导入和调用链 |
| 完整重写浪费 tokens | 描述变更，无需行号 |
| 行号错误破坏代码 | 10,000+ tokens/秒 合并 |

## 功能特性

- **快速应用** — 通过 Relace API 以 10,000+ tokens/秒的速度应用代码编辑
- **快速搜索** — 使用自然语言查询进行智能代码库探索
- **云端同步** — 将本地代码库上传到 Relace Cloud 进行语义搜索
- **云端搜索** — 对云端同步的仓库进行语义代码搜索
- **仪表盘** — 实时终端 UI 用于监控操作

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
| `RELACE_API_KEY` | ✅* | 来自 [Relace Dashboard](https://app.relace.ai/settings/billing) 的 API 密钥 |
| `RELACE_CLOUD_TOOLS` | ❌ | 设为 `1` 启用云端工具 |
| `SEARCH_LSP_TOOLS` | ❌ | LSP 工具：`1`（全开）、`auto`（检测已安装服务器）、`0`（关，默认） |
| `MCP_BASE_DIR` | ❌ | 项目根目录（自动检测：MCP Roots → Git → CWD） |
| `MCP_LOGGING` | ❌ | 设为 `1` 启用文件日志 |
| `MCP_DOTENV_PATH` | ❌ | `.env` 文件路径，用于集中配置 |

`*` 仅当**同时满足**：(1) `APPLY_PROVIDER` 与 `SEARCH_PROVIDER` 均为非 Relace 提供商，且 (2) `RELACE_CLOUD_TOOLS=false` 时可省略。

`.env` 使用方法、编码设置、自定义 LLM 等进阶设置，请参见 [docs/advanced.zh-CN.md](docs/advanced.zh-CN.md)。

## 工具

核心工具（`fast_apply`、`fast_search`）始终可用。云端工具需设置 `RELACE_CLOUD_TOOLS=1`。

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

使用标准代码定位数据集评估 `fast_search` 性能。

```bash
pip install relace-mcp[benchmark]
uv run python -m benchmark.cli.run --dataset artifacts/data/processed/elite_50.jsonl --limit 20
```

详细说明请参见 [docs/benchmark.zh-CN.md](docs/benchmark.zh-CN.md)。

## 平台支持

| 平台 | 状态 | 备注 |
|------|------|------|
| Linux | ✅ 完全支持 | 主要开发平台 |
| macOS | ✅ 完全支持 | 所有功能可用 |
| Windows | ⚠️ 部分支持 | `bash` 工具不可用；使用 WSL 以获得完整功能 |

## 故障排除

| 错误 | 解决方案 |
|------|----------|
| `RELACE_API_KEY is not set` | 在环境变量或 MCP 配置中设置密钥 |
| `NEEDS_MORE_CONTEXT` | 在目标块前后包含 1-3 行锚定行 |
| `FILE_TOO_LARGE` | 文件超过 10MB；拆分文件 |
| `ENCODING_ERROR` | 显式设置 `RELACE_DEFAULT_ENCODING` |
| `AUTH_ERROR` | 验证 API 密钥是否有效且未过期 |
| `RATE_LIMIT` | 请求过多；稍后重试 |

## 开发

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync --extra dev
uv run pytest
```

## 许可证

MIT
