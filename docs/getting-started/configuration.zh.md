# 配置

Relace MCP 完整配置指南。

## 环境变量

### 核心设置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `RELACE_API_KEY` | 是* | - | 从 [dashboard](https://app.relace.ai/settings/billing) 获取的 Relace API key |
| `RELACE_BASE_URL` | 否 | `https://api.relace.ai` | API base URL |
| `RELACE_LOG_LEVEL` | 否 | `INFO` | 日志级别:DEBUG, INFO, WARNING, ERROR |

\* `fast_apply` 需要。仅使用本地工具时可选填。

### 云端工具

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `RELACE_CLOUD_TOOLS` | 否 | `0` | 启用云端搜索工具 (0 或 1) |
| `RELACE_API_KEY` | 是** | - | 云端工具需要 |

\** 当 `RELACE_CLOUD_TOOLS=1` 时必需

### 高级搜索

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `MCP_SEARCH_RETRIEVAL` | 否 | `0` | 启用两阶段检索 (0 或 1) |
| `MCP_SEARCH_TIMEOUT` | 否 | `30` | 搜索超时秒数 |

### 性能

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `RELACE_MAX_RETRIES` | 否 | `3` | 最大 API 重试次数 |
| `RELACE_TIMEOUT` | 否 | `60` | 请求超时秒数 |

## MCP 客户端配置

### Cursor

编辑 `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "sk-...",
        "RELACE_LOG_LEVEL": "INFO",
        "RELACE_CLOUD_TOOLS": "1",
        "MCP_SEARCH_RETRIEVAL": "1"
      }
    }
  }
}
```

### Claude Desktop

=== "macOS"

    编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "sk-...",
            "RELACE_CLOUD_TOOLS": "1"
          }
        }
      }
    }
    ```

=== "Windows"

    编辑 `%APPDATA%\Claude\claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "sk-...",
            "RELACE_CLOUD_TOOLS": "1"
          }
        }
      }
    }
    ```

### Cline (VSCode)

添加到 `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "sk-...",
        "RELACE_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

## 配置预设

### 最小配置(仅本地)

无云端功能,仅本地搜索:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "0",
    "MCP_SEARCH_RETRIEVAL": "0"
  }
}
```

### 推荐配置

平衡功能与性能:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "1",
    "MCP_SEARCH_RETRIEVAL": "0",
    "RELACE_LOG_LEVEL": "INFO"
  }
}
```

### 最大功能

启用所有功能:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "1",
    "MCP_SEARCH_RETRIEVAL": "1",
    "RELACE_LOG_LEVEL": "DEBUG"
  }
}
```

### 性能优化

适用于大型代码库:

```json
{
  "env": {
    "RELACE_API_KEY": "sk-...",
    "RELACE_CLOUD_TOOLS": "0",
    "MCP_SEARCH_TIMEOUT": "60",
    "RELACE_MAX_RETRIES": "5"
  }
}
```

## 使用 .env 文件

在项目根目录创建 `.env` 文件:

```bash
# .env
RELACE_API_KEY=sk-...
RELACE_CLOUD_TOOLS=1
MCP_SEARCH_RETRIEVAL=1
RELACE_LOG_LEVEL=INFO
```

然后在 MCP 配置中引用:

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

!!! warning "安全性"
    切勿将包含 API key 的 `.env` 文件提交到版本控制。将 `.env` 加入 `.gitignore`。

## 日志

### 日志级别

- **DEBUG**:详细诊断信息
- **INFO**:一般信息消息(默认)
- **WARNING**:警告消息
- **ERROR**:仅错误消息

### 查看日志

=== "Cursor"

    1. 打开开发者工具:`Cmd+Option+I` (Mac) 或 `Ctrl+Shift+I` (Windows)
    2. 前往 Console 标签
    3. 筛选"relace-mcp"

=== "Claude Desktop"

    检查应用程序日志:

    - macOS: `~/Library/Logs/Claude/`
    - Windows: `%APPDATA%\Claude\logs\`

=== "Cline"

    1. 打开输出面板:`View > Output`
    2. 从下拉选单选择"Cline"

## 故障排除

??? question "API key 无效?"

    1. 验证 key 正确(无多余空格)
    2. 检查 [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. 确保环境变量设置正确
    4. 重启 MCP 客户端

??? question "云端工具无法使用?"

    1. 设置 `RELACE_CLOUD_TOOLS=1`
    2. 确保 API key 已设置
    3. 重启 MCP 客户端
    4. 检查日志错误消息

??? question "性能缓慢?"

    1. 安装 `ripgrep` 以加快搜索
    2. 若网络慢则增加超时时间
    3. 若不需要则禁用 `MCP_SEARCH_RETRIEVAL`
    4. 使用仅本地模式 (`RELACE_CLOUD_TOOLS=0`)

## 下一步

- [快速开始](quick-start.md) - 开始使用 Relace MCP
- [工具总览](../tools/index.md) - 了解可用工具
