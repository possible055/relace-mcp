# 工具总览

Relace MCP 提供多个强大的 AI 辅助代码编辑和探索工具。

如需查看完整的 tool schema（参数与返回结构），请参见 [工具参考](reference.md)。

## 核心工具

### Fast Apply

通过 Relace API 以 **10,000+ tokens/sec** 速度应用代码编辑。

```python
fast_apply(
    path="src/example.py",
    edit_snippet="def hello():\n    print('world')",
    instruction="Add hello function"
)
```

[:octicons-arrow-right-24: 了解更多 Fast Apply](fast-apply.md)

### Agentic Search

使用自然语言查询搜索代码库。

```python
agentic_search(
    query="用户认证在哪里实现？"
)
```

[:octicons-arrow-right-24: 了解更多 Agentic Search](agentic-search.md)

## 云端工具

!!! info "启用云端工具"
    设置 `RELACE_CLOUD_TOOLS=1` 启用云端工具。

### Cloud Sync

上传代码库以进行语义搜索。

```python
cloud_sync(force=False, mirror=False)
```

### Cloud Search

对云端同步的仓库进行语义搜索。

```python
cloud_search(query="认证逻辑")
```

[:octicons-arrow-right-24: 了解更多 Cloud Search](cloud-search.md)

## 高级工具

### Agentic Retrieval

两阶段语义 + 智能代码检索。

!!! info "启用 Retrieval"
    设置 `MCP_SEARCH_RETRIEVAL=1` 启用此工具。

```python
agentic_retrieval(
    query="验证 JWT token 的函数"
)
```

## 工具对比

| 工具 | 速度 | 准确度 | 使用案例 |
|------|------|--------|----------|
| `fast_apply` | ⚡⚡⚡ | 高 | 代码编辑 |
| `agentic_search` | ⚡⚡ | 非常高 | 本地搜索 |
| `cloud_search` | ⚡ | 高 | 跨仓库搜索 |
| `agentic_retrieval` | ⚡ | 非常高 | 复杂查询 |

## 下一步

- [Fast Apply](fast-apply.md) - 详细指南
- [Agentic Search](agentic-search.md) - 搜索策略
- [Cloud Search](cloud-search.md) - 云端配置
