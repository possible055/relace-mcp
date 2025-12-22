<p align="right">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

# 非官方 Relace MCP 服务器

[![PyPI](https://img.shields.io/pypi/v/relace-mcp.svg)](https://pypi.org/project/relace-mcp/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/possible055/relace-mcp/badge)](https://scorecard.dev/viewer/?uri=github.com/possible055/relace-mcp)

> **非官方** — 个人项目，与 Relace 无关联。
>
> **AI 构建** — 完全由 AI 辅助开发（Antigravity、Codex、Cursor、Github Copilot、Windsurf）。

[Relace](https://www.relace.ai/) 的 MCP 服务器 — AI 驱动的即时代码合并和智能代码库搜索。

## 功能特性

- **快速应用** — 通过 Relace API 以 10,000+ tokens/秒的速度应用代码编辑
- **快速搜索** — 使用自然语言查询进行智能代码库探索
- **云端同步** — 将本地代码库上传到 Relace Cloud 进行语义搜索
- **云端搜索** — 对云端同步的仓库进行语义代码搜索

## 快速开始

1. 从 [Relace Dashboard](https://app.relace.ai/settings/billing) 获取 API 密钥

2. 添加到你的 MCP 配置：

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

> **重要：** `RELACE_BASE_DIR` 必须设置为项目的绝对路径。这会限制文件访问范围并确保正确运行。

## 环境变量

| 变量 | 必需 | 描述 |
|------|------|------|
| `RELACE_API_KEY` | ✅ | 来自 [Relace Dashboard](https://app.relace.ai/settings/billing) 的 API 密钥 |
| `RELACE_BASE_DIR` | ✅ | 项目根目录的绝对路径 |
| `RELACE_STRICT_MODE` | ❌ | 设置 `1` 以强制要求显式 base dir（生产环境推荐） |

> 高级设置（开发者覆盖、提供商切换、远程部署）请参见 [docs/advanced.md](docs/advanced.md)。

## 工具

### `fast_apply`

对文件应用编辑（或创建新文件）。使用 `// ... existing code ...` 或 `# ... existing code ...` 等截断占位符。

**参数：**

| 参数 | 必需 | 描述 |
|------|------|------|
| `path` | ✅ | `RELACE_BASE_DIR` 内的绝对路径 |
| `edit_snippet` | ✅ | 带有缩写占位符的代码 |
| `instruction` | ❌ | 消歧提示 |

**示例：**

```json
{
  "path": "/home/user/project/src/file.py",
  "edit_snippet": "// ... existing code ...\nfunction newFeature() {}\n// ... existing code ...",
  "instruction": "Add new feature"
}
```

**返回：** 更改的 UDiff，或新文件的确认信息。

### `fast_search`

搜索代码库并返回相关文件和行范围。

**参数：** `query` — 自然语言搜索查询

**响应示例：**

```json
{
  "query": "How is authentication implemented?",
  "explanation": "Auth logic is in src/auth/...",
  "files": {
    "/home/user/project/src/auth/login.py": [[10, 80]]
  },
  "turns_used": 4
}
```

**参数：**
- `query` — 自然语言搜索查询

### `cloud_sync`

将本地代码库同步到 Relace Cloud 以进行语义搜索。将 `RELACE_BASE_DIR` 中的源文件上传到 Relace Repos。

**参数：**

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `force` | ❌ | `false` | 强制完整同步，忽略缓存状态 |
| `mirror` | ❌ | `false` | 配合 `force=True` 使用，完全覆盖云端仓库 |

**行为：**
- 遵循 `.gitignore` 模式（可用时使用 `git ls-files`）
- 支持 60+ 种常见源代码文件类型（`.py`、`.js`、`.ts`、`.java` 等）
- 跳过大于 1MB 的文件和常见非源代码目录（`node_modules`、`__pycache__` 等）
- 同步状态存储在 `~/.local/state/relace/sync/`

> 高级同步模式（增量、安全完整、镜像）请参见 [docs/advanced.md](docs/advanced.md#sync-modes)。

### `cloud_search`

对云端同步的仓库进行语义代码搜索。需要先运行 `cloud_sync`。

**参数：**

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `query` | ✅ | — | 自然语言搜索查询 |
| `branch` | ❌ | `""` | 要搜索的分支（空值使用 API 默认值） |
| `score_threshold` | ❌ | `0.3` | 最低相关性分数（0.0-1.0） |
| `token_limit` | ❌ | `30000` | 返回的最大 token 数 |

### `cloud_list`

列出 Relace Cloud 账户中的所有仓库。

**参数：** 无

### `cloud_info`

获取当前仓库的详细同步状态。在 `cloud_sync` 之前使用以了解需要执行的操作。

**参数：** 无

### `cloud_clear`

删除云端仓库和本地同步状态。在切换项目或重大重构后重置时使用。

**参数：**

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `confirm` | ✅ | `false` | 必须为 `true` 才能继续（安全保护） |

**返回：**

```json
{
  "deleted": true,
  "repo_id": "uuid",
  "state_cleared": true
}
```

## 日志

> **注意：** 文件日志功能为实验性功能。使用 `RELACE_EXPERIMENTAL_LOGGING=1` 启用。

操作日志写入 `~/.local/state/relace/relace_apply.log`。

## 故障排除

常见问题：
- `RELACE_API_KEY is not set`：在环境变量或 MCP 配置中设置密钥。
- `RELACE_BASE_DIR does not exist` / `INVALID_PATH`：确保路径存在且在 `RELACE_BASE_DIR` 范围内。
- `NEEDS_MORE_CONTEXT`：在目标块前后包含 1-3 行真实的锚定行。

## 开发

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv sync
uv run pytest
```
