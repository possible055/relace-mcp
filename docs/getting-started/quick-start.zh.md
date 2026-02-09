# 快速入门

5 分钟上手 Relace MCP。

## 前置需求

开始前请确认已安装:

- [x] [uv](https://docs.astral.sh/uv/)
- [x] [git](https://git-scm.com/)
- [x] [ripgrep](https://github.com/BurntSushi/ripgrep) (推荐)

## 安装

### 获取 API Key

!!! tip "Relace API Key"
    从 [Relace Dashboard](https://app.relace.ai/settings/billing) 获取 API key

### 配置

设置 MCP 客户端使用 Relace MCP。

=== "AmpCode"

    添加到 MCP 客户端配置:

    - **Server Name**: `relace`
    - **Command or URL**: `uv`
    - **Arguments (whitespace-separated)**: `tool run relace-mcp`
    - **Environment Variables**:
        - `RELACE_API_KEY` = `your-api-key-here`
        - `MCP_BASE_DIR` = `/path/to/your/project`

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
          }
        }
      }
    }
    ```

=== "Claude Code"

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
          }
        }
      }
    }
    ```

=== "Codex"

    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]
    startup_timeout_sec = 30
    tool_timeout_sec = 60

    [mcp_servers.relace.env]
    RELACE_API_KEY = "your-api-key-here"
    MCP_BASE_DIR = "/path/to/your/project"
    ```

=== "Windsurf"

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here",
            "MCP_BASE_DIR": "/path/to/your/project"
          }
        }
      }
    }
    ```

=== "其他客户端"

    添加到 MCP 客户端配置:

    - **Command**: `uv`
    - **Args**: `["tool", "run", "relace-mcp"]`
    - **Environment**:
        - `RELACE_API_KEY` = `your-api-key-here`
        - `MCP_BASE_DIR` = `/path/to/your/project`

!!! tip "进阶配置"
    如需启用云端工具、调试模式或自定义 provider，请参见 [环境变量](../advanced/environment-variables.md)。

## 验证安装

配置完成后重启 MCP 客户端，你应该看到以下工具：

- `fast_apply` - 快速代码编辑
- `agentic_search` - 语义代码搜索

完整工具列表请参见 [工具总览](../tools/overview.md)。

## 故障排除

??? question "工具没有显示?"

    1. 检查 MCP 客户端日志
    2. 验证 `uv tool list` 显示 `relace-mcp`
    3. 重启 MCP 客户端
    4. 检查环境变量设置正确

??? question "API key 错误?"

    1. 验证 API key 正确
    2. 检查 [Relace Dashboard](https://app.relace.ai/settings/billing)
    3. 确保环境变量无多余空格

??? question "性能缓慢?"

    1. 安装 `ripgrep` 以加快搜索
    2. 检查网络连接
    3. 启用 debug 日志:`MCP_LOG_LEVEL=DEBUG`

需要更多帮助? [打开 issue](https://github.com/possible055/relace-mcp/issues)。

## 下一步

- **配置指南**: 查看 [配置](../configuration/overview.md) 了解自定义 Provider 與功能开关
- **环境变量**: 查看 [环境变量](../advanced/environment-variables.md) 了解所有选项
- **工具总览**: 探索 [工具总览](../tools/overview.md) 了解 Relace MCP 的功能
