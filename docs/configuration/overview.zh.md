# 概览

Relace MCP 支持使用自定义模型提供商与 RAG 分块代码索引服务，不会受到单一商业服务局限。

## 环境变量

使用环境变量配置功能与自定义提供商。详细变量说明请参阅[环境变量](../advanced/environment-variables.md)完整参考。

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
    RELACE_API_KEY = "your_relace_api_key"
    RELACE_CLOUD_TOOLS = "1"

    # 代理搜寻相关设置
    SEARCH_PROVIDER = "openai"
    SEARCH_ENDPOINT = "https://api.openai.com/v1"
    OPENAI_API_KEY = "your_api_key"
    SEARCH_MODEL = "gpt-4o"
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
    RELACE_API_KEY = "your_relace_api_key"

    # 代理搜寻相关设置
    SEARCH_PROVIDER = "openai"
    SEARCH_ENDPOINT = "https://api.openai.com/v1"
    OPENAI_API_KEY = "your_openai_api_key"
    SEARCH_MODEL = "gpt-4o"
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
            "SEARCH_MODEL": "gpt-4o"
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
            "SEARCH_MODEL": "gpt-4o"
            "SEARCH_LSP_TOOLS": "1"
            "MCP_SEARCH_RETRIEVAL": "1"
            "MCP_RETRIEVAL_BACKEND": "codanna"
          }
        }
      }
    }
    ```
