# 快速开始

5 分钟上手 Relace MCP。

## 前置需求

开始前请确认已安装:

- [x] [uv](https://docs.astral.sh/uv/)
- [x] [git](https://git-scm.com/)
- [x] [ripgrep](https://github.com/BurntSushi/ripgrep)(推荐)

## 安装

### 方案 1:使用 uv(推荐)

```bash
uv tool install relace-mcp
```

### 方案 2:使用 pip

```bash
pip install relace-mcp
```

### 方案 3:从源代码安装

```bash
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp
uv pip install -e .
```

## 获取 API Key

!!! tip "Relace API Key"
    从 [Relace Dashboard](https://app.relace.ai/settings/billing) 获取 API key

## 配置

设置 MCP 客户端使用 Relace MCP。

=== "Cursor"

    编辑 `~/.cursor/mcp.json`:

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here"
          }
        }
      }
    }
    ```

=== "Claude Desktop"

    编辑 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here"
          }
        }
      }
    }
    ```

=== "Cline (VSCode)"

    编辑 VSCode 设置 (`.vscode/settings.json` 或 User Settings):

    ```json
    {
      "mcp.servers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your-api-key-here"
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
        - `RELACE_API_KEY`: your-api-key-here

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `RELACE_API_KEY` | 是* | - | Relace API key |
| `RELACE_CLOUD_TOOLS` | 否 | `0` | 启用云端搜索工具 |
| `MCP_SEARCH_RETRIEVAL` | 否 | `0` | 启用两阶段检索 |
| `MCP_LOG_LEVEL` | 否 | `WARNING` | 日志级别 (DEBUG, INFO, WARNING, ERROR) |

!!! note "API Key 需求"
    默认情况下（Relace provider），需要 `RELACE_API_KEY`。若你通过 `APPLY_PROVIDER` / `SEARCH_PROVIDER` 切换 provider，请改为设置对应 provider 的 API key。

## 验证安装

重启 MCP 客户端并确认 `fast_apply` 与 `agentic_search` 可用。

- 若 `RELACE_CLOUD_TOOLS=1`，你也应看到 `cloud_*` 工具。
- 若 `MCP_SEARCH_RETRIEVAL=1`，你也应看到 `agentic_retrieval`。

完整工具列表与 schema 请参见 [工具总览](../tools/index.md) 与 [工具参考](../tools/reference.md)。

## 首次使用

### 1. 搜索代码库

使用自然语言搜索代码:

```
使用 agentic_search 找出认证逻辑在哪里
```

### 2. 应用代码变更

使用 `fast_apply` 进行变更:

```
使用 fast_apply 为认证函数添加错误处理
```

### 3. 启用云端搜索(可选)

如需跨仓库搜索:

1. 设置 `RELACE_CLOUD_TOOLS=1`
2. 重启 MCP 客户端
3. 同步仓库:使用 `cloud_sync`
4. 跨仓库搜索:使用 `cloud_search`

## 下一步

- [安装指南](installation.md) - 详细安装选项
- [配置指南](configuration.md) - 高级配置
- [工具总览](../tools/index.md) - 了解可用工具

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

需要更多帮助?[打开 issue](https://github.com/possible055/relace-mcp/issues)。
