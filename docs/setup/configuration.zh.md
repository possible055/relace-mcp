# 配置

配置 MCP 客户端以运行 Relace MCP。

## 常用环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `RELACE_API_KEY` | 是* | — | 默认 Relace provider 的 API key |
| `RELACE_CLOUD_TOOLS` | 否 | `0` | 启用 `cloud_*` 工具 |
| `MCP_SEARCH_RETRIEVAL` | 否 | `0` | 启用 `agentic_retrieval` |
| `MCP_LOG_LEVEL` | 否 | `WARNING` | 日志级别：DEBUG, INFO, WARNING, ERROR |
| `MCP_BASE_DIR` | 否 | auto | 将文件访问限制在该目录内 |

\* 当使用默认 Relace provider（`APPLY_PROVIDER=relace` / `SEARCH_PROVIDER=relace`，默认）时必需；当 `RELACE_CLOUD_TOOLS=1` 时也必需。

完整的环境变量参考（providers、timeouts、logging、remote deployment）请参见 [Advanced](../advanced/index.md)。

## MCP 客户端配置

### Cursor

编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "your-api-key-here",
        "RELACE_CLOUD_TOOLS": "0",
        "MCP_SEARCH_RETRIEVAL": "0",
        "MCP_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

### Claude Desktop

=== "macOS"

    编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "RELACE_CLOUD_TOOLS": "0"
          }
        }
      }
    }
    ```

=== "Windows"

    编辑 `%APPDATA%\\Claude\\claude_desktop_config.json`：

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "RELACE_CLOUD_TOOLS": "0"
          }
        }
      }
    }
    ```

### Cline (VSCode)

添加到 `.vscode/settings.json`：

```json
{
  "mcp.servers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "your-api-key-here",
        "MCP_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

## 常见问题

??? question "API key 报错？"

    1. 确认 key 正确（无多余空格）
    2. 检查 [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. 若你设置了 `APPLY_PROVIDER` / `SEARCH_PROVIDER`，请确认对应的 `*_API_KEY` 已设置

??? question "需要 debug 日志？"

    设置 `MCP_LOG_LEVEL=DEBUG` 并重启 MCP 客户端。

## 下一步

- [快速开始](../getting-started/quick-start.md) - 5 分钟上手
- [工具总览](../tools/index.md) - 了解可用工具
- [Advanced](../advanced/index.md) - 完整配置参考
