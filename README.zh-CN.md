<p align="right">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

# 非官方 Relace MCP 服务器

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
![100% AI生成](https://img.shields.io/badge/100%25%20AI-Generated-ff69b4.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/possible055/relace-mcp/badge)](https://scorecard.dev/viewer/?uri=github.com/possible055/relace-mcp)
[![MCP Badge](https://lobehub.com/badge/mcp/possible055-relace-mcp)](https://lobehub.com/mcp/possible055-relace-mcp)

> **非官方** — 个人项目，与 Relace 无关联。
>
> **AI 构建** — 完全由 AI 辅助开发（Antigravity、Codex、Cursor、Github Copilot、Windsurf）。

[Relace](https://www.relace.ai/) 的 MCP 服务器 — AI 驱动的即时代码合并和智能代码库搜索。

## 前置需求

- [uv](https://docs.astral.sh/uv/) — Python 包管理器
- [git](https://git-scm.com/) — 用于让 `cloud_sync` 遵循 `.gitignore`
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) — 推荐用于 `fast_search`（未安装时会退化为 Python 正则匹配）

### 平台支持

| 平台 | 状态 | 备注 |
|------|------|------|
| Linux | ✅ 完全支持 | 主要开发平台 |
| macOS | ✅ 完全支持 | 所有功能可用 |
| Windows | ⚠️ 部分支持 | `bash` 工具不可用；使用 WSL 以获得完整功能 |

> **Windows 用户：** `bash` 工具需要 Unix shell。安装 [WSL](https://learn.microsoft.com/windows/wsl/install) 以获得完整功能，或使用其他探索工具（`view_file`、`grep_search`、`glob`）。

## 快速开始

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

> **注意：** `RELACE_BASE_DIR` 可选。若未设置，服务器会自动检测项目根目录（通过 MCP Roots 或 Git 仓库）。

## 功能特性

- **快速应用** — 通过 Relace API 以 10,000+ tokens/秒的速度应用代码编辑
- **快速搜索** — 使用自然语言查询进行智能代码库探索
- **云端同步** — 将本地代码库上传到 Relace Cloud 进行语义搜索
- **云端搜索** — 对云端同步的仓库进行语义代码搜索
- **仪表盘** — 实时终端 UI 用于监控操作（需要 `textual`）

## 环境变量

| 变量 | 必需 | 描述 |
|------|------|------|
| `RELACE_API_KEY` | ✅ | 来自 [Relace Dashboard](https://app.relace.ai/settings/billing) 的 API 密钥 |
| `RELACE_BASE_DIR` | ❌ | 项目根目录的绝对路径（未设置时自动通过 MCP Roots 检测） |
| `RELACE_DOTENV_PATH` | ❌ | `.env` 文件路径，用于集中配置 |
| `RELACE_CLOUD_TOOLS` | ❌ | 设为 `1` 启用云端工具（cloud_sync、cloud_search 等） |
| `RELACE_LOGGING` | ❌ | 设为 `1` 启用文件日志（默认：禁用） |
| `RELACE_DEFAULT_ENCODING` | ❌ | 强制文件编码（如 `gbk`、`big5`），用于遗留编码仓库 |
| `RELACE_TEMPERATURE` | ❌ | LLM 采样温度（默认：`1.0`，范围：0.0-2.0） |

### 使用 .env 文件

可以使用集中的 `.env` 文件代替在 MCP 配置中设置多个环境变量：

**1. 创建 `.env` 文件**（例如 `~/.config/relace/.env`）：

```bash
# ~/.config/relace/.env
RELACE_API_KEY=rlc-your-api-key

# 自定义搜索模型（可选）
SEARCH_PROVIDER=openai
SEARCH_ENDPOINT=https://api.openai.com/v1
SEARCH_MODEL=gpt-4o
SEARCH_API_KEY=sk-xxx

# 其他设置
RELACE_LOGGING=1
SEARCH_MAX_TURNS=6
```

**2. 在 MCP 配置中指向该文件：**

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_DOTENV_PATH": "~/.config/relace/.env"
      }
    }
  }
}
```

> **注意：** 直接在 `env` 中设置的变量优先于 `.env` 文件中的变量。

> **注意：** 当 `RELACE_BASE_DIR` 未设置时，服务器会自动检测项目根目录：
> 1. MCP Roots（编辑器提供的工作区信息）
> 2. Git 仓库根目录（若存在）
> 3. 当前工作目录（后备方案）
>
> ⚠️ **警告：** 若 MCP Roots 获取失败，隐式回退到 CWD 可能导致不稳定。建议显式设置 `RELACE_BASE_DIR`。

> 高级设置请参见 [docs/advanced.zh-CN.md](docs/advanced.zh-CN.md)。

## 工具

### 核心工具（始终可用）

| 工具 | 描述 |
|------|------|
| `fast_apply` | 以 10,000+ tokens/秒的速度应用代码编辑 |
| `fast_search` | 使用自然语言进行智能代码库搜索 |

### 云端工具（需设置 `RELACE_CLOUD_TOOLS=1`）

| 工具 | 描述 |
|------|------|
| `cloud_sync` | 将本地代码库上传到 Relace Cloud |
| `cloud_search` | 对云端同步的仓库进行语义搜索 |
| `cloud_list` | 列出云端仓库 |
| `cloud_info` | 获取同步状态 |
| `cloud_clear` | 删除云端仓库和本地状态 |

> 详细参数和示例请参见 [docs/tools.zh-CN.md](docs/tools.zh-CN.md).

## 日志

> **注意：** 文件日志为可选功能。使用 `RELACE_LOGGING=1` 启用。

操作日志写入跨平台状态目录：
- **Linux**: `~/.local/state/relace/relace.log`
- **macOS**: `~/Library/Application Support/relace/relace.log`
- **Windows**: `%LOCALAPPDATA%\relace\relace.log`

> 日志格式和进阶选项请参见 [docs/advanced.zh-CN.md](docs/advanced.zh-CN.md#日志)。

## 仪表盘

实时终端 UI，用于监控 `fast_apply` 和 `fast_search` 操作。

```bash
# 安装包含仪表盘支持
pip install relace-mcp[tools]

# 启动仪表盘
relace-dashboard
```

功能特性：
- 多视图标签页（All、Apply、Search、Insights、Errors）
- 时间范围筛选（1h、6h、24h、All）
- 实时日志追踪
- 树形结构搜索会话视图
- 工具使用统计

> 详细用法请参见 [docs/dashboard.zh-CN.md](docs/dashboard.zh-CN.md)。

## 故障排除

常见问题：
- `RELACE_API_KEY is not set`：在环境变量或 MCP 配置中设置密钥。
- `RELACE_BASE_DIR does not exist` / `INVALID_PATH`：确保路径存在且在 `RELACE_BASE_DIR` 范围内。
- `NEEDS_MORE_CONTEXT` / `APPLY_NOOP`：在目标块前后包含 1-3 行真实的锚定行。
- `FILE_TOO_LARGE`：文件超过 1MB 大小限制；拆分大文件或增加限制。
- `ENCODING_ERROR`：无法检测文件编码；显式设置 `RELACE_DEFAULT_ENCODING`。
- `FILE_NOT_WRITABLE` / `PERMISSION_ERROR`：检查文件和目录的写入权限。
- `AUTH_ERROR`：验证 `RELACE_API_KEY` 是否有效且未过期。
- `RATE_LIMIT`：请求过多；稍后重试。
- `TIMEOUT_ERROR` / `NETWORK_ERROR`：检查网络连接；通过 `APPLY_TIMEOUT_SECONDS` 增加超时时间。

> **Windows 用户：** `fast_search` 中的 `bash` 工具在 Windows 上不可用。请使用 WSL 或依赖其他探索工具（`view_file`、`grep_search`、`glob`）。

## 开发

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync --extra dev
uv run pytest

# Lint / 类型检查（可选）
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run basedpyright --level error
