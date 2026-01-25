# ChunkHound 配置

Relace MCP 支持使用 **ChunkHound** 作为高性能的本地语义搜索后端。

## 安装

安装 ChunkHound CLI：

```bash
uv tool install chunkhound
# 或者
pip install chunkhound
```

## 配置

要启用 ChunkHound 作为检索后端，请设置以下环境变量：

```bash
export MCP_RETRIEVAL_BACKEND="chunkhound"
```

### 客户端配置

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "relace": {
          "env": {
            "RELACE_API_KEY": "your-key",
            "MCP_RETRIEVAL_BACKEND": "chunkhound",
            "MCP_SEARCH_RETRIEVAL": "1"
          }
        }
      }
    }
    ```

## 索引 (Indexing)

Relace MCP 会自动处理索引。

1.  **自动索引**：当执行搜索时，如果索引不存在，Relace 将尝试为当前目录自动生成索引。
2.  **手动索引**：您也可以手动运行索引命令：

    ```bash
    cd /path/to/project
    chunkhound index
    ```
