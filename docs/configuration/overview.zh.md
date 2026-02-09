# 概览

Relace MCP 支持使用自定义模型提供商与 RAG 分块代码索引服务，不会受到单一商业服务局限。

## 环境变量

使用环境变量启用可选或实验性功能。详细变量说明与调整可于[高级-环境变量](../advanced/environment-variables.md)中查阅。

### 功能开关

| 变量 | 说明 |
|---|---|
| `RELACE_CLOUD_TOOLS` | 设置为 `1` 启用 Relace Cloud 工具。 |
| `SEARCH_LSP_TOOLS` | 设置为 `1` 启用 LSP 工具。 |
| `MCP_BASE_DIR` | 限制文件操作的根目录。未设置时，服务器从 MCP Roots 解析。 |
| `MCP_LOGGING` | 本地 JSONL 日志：`off` (默认), `safe` (脱敏), `full` (完整)。 |
| `MCP_SEARCH_RETRIEVAL` | 设置为 `1` 启用两阶段检索。 |
| `MCP_RETRIEVAL_BACKEND` | `relace` (默认), `codanna` (本地), `chunkhound` (本地), 或 `none` (禁用)。 |

### 自定义模型

除了 Relace 官方服务，也可以采用其他模型作为代理搜寻与快速应用的代理模型。

**快速应用**

| 变量 | 说明 |
|---|---|
| `APPLY_PROVIDER` | 提供商名称，如 `openai`、`openrouter`、`cerebras` 等。 |
| `APPLY_ENDPOINT` | 提供商 OpenAI 兼容端点。 |
| `APPLY_API_KEY` | 提供商 API 密钥。 |
| `APPLY_MODEL` | 快速应用使用的模型，默认 `auto`。 |

**代理搜寻**

| 变量 | 说明 |
|---|---|
| `SEARCH_PROVIDER` | 提供商名称，如 `openai`、`mistral` 等。 |
| `SEARCH_ENDPOINT` | 提供商 OpenAI 兼容端点，如 `https://api.openai.com/v1`。 |
| `SEARCH_API_KEY` | 提供商 API 密钥（或使用 `OPENAI_API_KEY` / `MISTRAL_API_KEY`）。 |
| `SEARCH_MODEL` | 语意搜寻使用的模型，如 `gpt-4o`、`devstral-small-2505`。 |

## 配置示例

以下展示不同客户端的配置范例。

### Codex

???+ example "默认 Relace 配置 + 启用 LSP 工具 + 启用检索增强服务"
    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]

    [mcp_servers.relace.env]
    RELACE_API_KEY = "your_relace_api_key"
    RELACE_CLOUD_TOOLS = "1"

    # 代理搜寻相关设置
    SEARCH_LSP_TOOLS = "1"

    # 混合搜寻相关设置
    MCP_SEARCH_RETRIEVAL = "1"
    ```

??? example "代理搜寻采用 OpenAI 提供商模型"
    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]

    [mcp_servers.relace.env]
    RELACE_API_KEY = "rlc-lB7ljkzOg051PN0av4HjaG-OC9aDcgA2Pbvt8g"
    RELACE_CLOUD_TOOLS = "1"

    # 代理搜寻相关设置
    SEARCH_PROVIDER = "openai"
    SEARCH_ENDPOINT = "https://api.openai.com/v1"
    OPENAI_API_KEY = "your_api_key"
    SEARCH_MODEL = "gpt-5.2"
    SEARCH_LSP_TOOLS = "1"

    # 混合搜寻相关设置
    MCP_SEARCH_RETRIEVAL = "1"
    ```

??? example "代理搜寻采用 OpenAI 提供商模型，检索增强采用 codanna 项目"
    ```toml
    [mcp_servers.relace]
    command = "uv"
    args = ["tool", "run", "relace-mcp"]

    [mcp_servers.relace.env]
    RELACE_API_KEY = "rlc-lB7ljkzOg051PN0av4HjaG-OC9aDcgA2Pbvt8g"

    # 代理搜寻相关设置
    SEARCH_PROVIDER = "openai"
    SEARCH_ENDPOINT = "https://api.openai.com/v1"
    OPENAI_API_KEY = "your_openai_api_key"
    SEARCH_MODEL = "gpt-5.2"
    SEARCH_LSP_TOOLS = "1"

    # 混合搜寻相关设置
    MCP_SEARCH_RETRIEVAL = "1"
    MCP_RETRIEVAL_BACKEND = "codanna"
    ```

### Cursor

???+ example "默认 Relace 配置 + 启用 LSP 工具 + 启用检索增强服务"
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your_relace_api_key"
            "RELACE_CLOUD_TOOLS": "1"
            "SEARCH_LSP_TOOLS": "1"
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

??? example "代理搜寻采用 OpenAI 提供商模型"
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your_relace_api_key"
            "RELACE_CLOUD_TOOLS": "1"
            "SEARCH_PROVIDER": "openai",
            "OPENAI_API_KEY": "your_openai_api_key",
            "SEARCH_MODEL": "gpt-5.2"
            "SEARCH_LSP_TOOLS": "1"
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

??? example "代理搜寻采用 OpenAI 提供商模型，检索增强采用 codanna 项目"
    ```json
    {
      "mcpServers": {
        "relace": {
          "command": "uv",
          "args": ["tool", "run", "relace-mcp"],
          "env": {
            "RELACE_API_KEY": "your_relace_api_key"
            "SEARCH_PROVIDER": "openai",
            "OPENAI_API_KEY": "your_openai_api_key",
            "SEARCH_MODEL": "gpt-5.2"
            "SEARCH_LSP_TOOLS": "1"
            "MCP_SEARCH_RETRIEVAL": "1"
            "MCP_RETRIEVAL_BACKEND": "codanna"
          }
        }
      }
    }
    ```
