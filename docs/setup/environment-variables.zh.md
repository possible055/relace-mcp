# 环境变量

Relace MCP 所有环境变量的完整参考。

## 核心变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `RELACE_API_KEY` | 是* | — | 从 [Dashboard](https://app.relace.ai/settings/billing) 获取的 Relace API key |
| `MCP_BASE_DIR` | 否 | auto | 限制文件操作的目录范围 |
| `MCP_LOGGING` | 否 | `off` | 日志模式：`off`、`safe`、`full` |

\* 使用 Relace provider（默认）或 `RELACE_CLOUD_TOOLS=1` 时必需。

## 可选功能

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RELACE_CLOUD_TOOLS` | `0` | 启用云端搜索工具（`cloud_sync`、`cloud_search` 等） |
| `MCP_SEARCH_RETRIEVAL` | `0` | 启用两阶段检索工具 `agentic_retrieval` |
| `SEARCH_LSP_TOOLS` | `0` | 启用 LSP 工具（实验性） |

## Provider 配置

覆盖默认 provider：

| 变量 | 默认值 | 选项 | 说明 |
|------|--------|------|------|
| `APPLY_PROVIDER` | `relace` | `relace`、`openai`、`anthropic` | 代码编辑 provider |
| `SEARCH_PROVIDER` | `relace` | `relace`、`openai`、`anthropic` | 代码搜索 provider |

切换 provider 时，需设置对应的 API key：
- **OpenAI**：`OPENAI_API_KEY`
- **Anthropic**：`ANTHROPIC_API_KEY`

## 日志与调试

| 变量 | 默认值 | 选项 | 说明 |
|------|--------|------|------|
| `MCP_LOG_LEVEL` | `WARNING` | `DEBUG`、`INFO`、`WARNING`、`ERROR` | Python 日志级别 |
| `MCP_LOGGING` | `off` | `off`、`safe`、`full` | MCP 传输层日志 |

**日志模式：**
- `off`：无 MCP 日志
- `safe`：脱敏日志（无敏感数据）
- `full`：完整协议日志

## 超时设置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RELACE_TIMEOUT` | `60` | 请求超时（秒） |
| `APPLY_TIMEOUT` | `60` | 代码编辑超时 |
| `SEARCH_TIMEOUT` | `60` | 搜索超时 |

## 高级配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RELACE_BASE_URL` | `https://api.relace.ai` | API 端点（用于自托管） |
| `DISABLE_GITIGNORE` | `0` | 忽略 `.gitignore` 规则 |

## 配置示例

### 最小配置（快速入门）

```bash
export RELACE_API_KEY="your-key-here"
export MCP_BASE_DIR="/path/to/project"
```

### 启用云端工具

```bash
export RELACE_API_KEY="your-key-here"
export RELACE_CLOUD_TOOLS="1"
export MCP_SEARCH_RETRIEVAL="1"
```

### 调试模式

```bash
export RELACE_API_KEY="your-key-here"
export MCP_LOG_LEVEL="DEBUG"
export MCP_LOGGING="safe"
```

### 替代 Provider（OpenAI）

```bash
export OPENAI_API_KEY="your-openai-key"
export APPLY_PROVIDER="openai"
export SEARCH_PROVIDER="openai"
```

## 参见

- [快速入门](../getting-started/quick-start.md) - 基本设置
- [配置](configuration.md) - MCP 客户端配置
- [高级](../advanced/index.md) - 高级用法
