# 配置

使用高级功能和自定义 Provider 定制 Relace MCP。

## 功能开关 (Feature Flags)

使用环境变量启用实验性或可选功能。

| 功能 | 变量 | 说明 |
|---|---|---|
| **检索增强 (Retrieval)** | `MCP_SEARCH_RETRIEVAL` | 设置为 `1` 启用两阶段检索 (RAG)。 |
| **LSP 工具** | `SEARCH_LSP_TOOLS` | 设置为 `1` 启用基于 LSP 的导航（跳转定义）。 |
| **云端工具** | `RELACE_CLOUD_TOOLS` | 设置为 `1` 启用 Relace Cloud 工具。 |
| **检索后端** | `MCP_RETRIEVAL_BACKEND` | `relace` (默认), `codanna` (本地), 或 `chunkhound`。 |

## 自定义 Provider

使用您自己的 API Key 进行模型推理。

| Provider | 变量 | API Key 变量 |
|---|---|---|
| **OpenAI** | `APPLY_PROVIDER=openai` | `OPENAI_API_KEY` |
| **Anthropic** | `APPLY_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |

## 配置示例

如何在您的客户端应用这些设置。

### Codex (TOML)

使用 OpenAI Provider 并启用 LSP 工具的 Codex 配置示例。

```toml
[mcp_servers.relace]
command = "uv"
args = ["tool", "run", "relace-mcp"]

[mcp_servers.relace.env]
# Provider Settings
APPLY_PROVIDER = "openai"
SEARCH_PROVIDER = "openai"
OPENAI_API_KEY = "sk-..."

# Feature Flags
SEARCH_LSP_TOOLS = "1"
MCP_RETRIEVAL_BACKEND = "codanna"
```

### Cursor (JSON)

使用 Anthropic Provider 并启用 Retrieval 的 Cursor 配置示例。

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "RELACE_API_KEY": "your-api-key-here",
        "APPLY_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "MCP_SEARCH_RETRIEVAL": "1"
      }
    }
  }
}
```

## 参见

- [环境变量](../advanced/environment-variables.md) - 完整参考指南
