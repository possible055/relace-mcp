# Codanna 配置

Relace MCP 支持使用 **Codanna** 作为语义搜索 (Retrieval) 的本地后端。

## 前置要求

请确保 `codanna` CLI 已安装并在您的系统 `PATH` 中可用。

```bash
# 验证安装
codanna --version
```

## 配置

要启用 Codanna 作为检索后端，请设置以下环境变量：

```bash
export MCP_RETRIEVAL_BACKEND="codanna"
```

### 客户端配置

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "relace": {
          "env": {
            "RELACE_API_KEY": "your-key",
            "MCP_RETRIEVAL_BACKEND": "codanna",
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

=== "Claude Desktop"

    ```json
    {
      "mcpServers": {
        "relace": {
          "env": {
            "RELACE_API_KEY": "your-key",
            "MCP_RETRIEVAL_BACKEND": "codanna",
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

## 使用說明

启用后，`agentic_retrieval` 工具将自动调用本地 `codanna` CLI 执行搜索。

Relace 執行指令：
```bash
codanna mcp semantic_search_with_context query:YOUR_QUERY ...
```
