<p align="right">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

# 非官方 Relace MCP 服务器

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![100% AI生成](https://img.shields.io/badge/100%25%20AI-Generated-ff69b4.svg)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/possible055/relace-mcp/badge)](https://scorecard.dev/viewer/?uri=github.com/possible055/relace-mcp)

> **非官方** — 个人项目，与 Relace 无关联。
>
> **AI 构建** — 完全由 AI 辅助开发（Antigravity、Codex、Cursor、Github Copilot、Windsurf）。

[Relace](https://www.relace.ai/) 的 MCP 服务器 — AI 驱动的即时代码合并和智能代码库搜索。

**`fast_apply`** 使用推测性编辑以 10,000+ tokens/秒的速度合并代码变更 — 无需行号或完整文件重写。**`fast_search`** 运行智能循环，使用自然语言探索代码库，返回与查询相关的文件和行范围。

## 功能特性

- **快速应用** — 通过 Relace API 以 10,000+ tokens/秒的速度应用代码编辑
- **快速搜索** — 使用自然语言查询进行智能代码库探索
- **云端同步** — 将本地代码库上传到 Relace Cloud 进行语义搜索
- **云端搜索** — 对云端同步的仓库进行语义代码搜索
- **仪表盘** — 实时终端 UI 用于监控操作

## 快速开始

**前置需求：** [uv](https://docs.astral.sh/uv/)、[git](https://git-scm.com/)、[ripgrep](https://github.com/BurntSushi/ripgrep)（推荐）

从 [Relace Dashboard](https://app.relace.ai/settings/billing) 获取 API 密钥，然后添加到你的 MCP 客户端：

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

## 配置

| 变量 | 必需 | 说明 |
|------|------|------|
| `RELACE_API_KEY` | ✅ | 来自 [Relace Dashboard](https://app.relace.ai/settings/billing) 的 API 密钥 |
| `RELACE_BASE_DIR` | ❌ | 项目根目录（自动检测：MCP Roots → Git → CWD） |
| `RELACE_DOTENV_PATH` | ❌ | `.env` 文件路径，用于集中配置 |
| `RELACE_CLOUD_TOOLS` | ❌ | 设为 `1` 启用云端工具 |
| `RELACE_LOGGING` | ❌ | 设为 `1` 启用文件日志 |

`.env` 使用方法、编码设置、自定义 LLM 等进阶设置，请参见 [docs/advanced.zh-CN.md](docs/advanced.zh-CN.md)。

## 工具

核心工具（`fast_apply`、`fast_search`）始终可用。云端工具需设置 `RELACE_CLOUD_TOOLS=1`。

详细参数请参见 [docs/tools.zh-CN.md](docs/tools.zh-CN.md)。

## 仪表盘

实时终端 UI，用于监控操作。

```bash
pip install relace-mcp[tools]
relogs
```

详细用法请参见 [docs/dashboard.zh-CN.md](docs/dashboard.zh-CN.md)。

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
| `FILE_TOO_LARGE` | 文件超过 1MB；拆分或增加限制 |
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
