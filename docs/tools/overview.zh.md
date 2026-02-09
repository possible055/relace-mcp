# 工具

Relace MCP 提供 AI 辅助代码编辑与探索工具。

## fast_apply

以行级精确合并对文件应用编辑（或创建新文件）。

**前置要求：** 设置 `RELACE_API_KEY`（默认 provider）。替代 provider 请参见 [Advanced](../advanced/overview.md)。

| 参数 | 必需 | 说明 |
|------|------|------|
| `path` | ✅ | 文件路径（绝对或相对 `MCP_BASE_DIR`） |
| `edit_snippet` | ✅ | 带截断占位符的代码片段 |
| `instruction` | ❌ | 消歧提示 |

使用截断占位符以保持上下文精简：

- `// ... existing code ...`（C/JS/TS）
- `# ... existing code ...`（Python/shell）

```json
{
  "path": "src/example.py",
  "edit_snippet": "# ... existing code ...\n\ndef hello():\n    print('world')\n\n# ... existing code ...",
  "instruction": "Add hello() helper"
}
```

返回更改的 UDiff，或新文件的确认信息。

!!! tip
    - 当编辑位置不明确时，提供 `instruction`。
    - 若出现 `NEEDS_MORE_CONTEXT`，补充目标前后几行真实代码。

## agentic_search

使用自然语言查询搜索代码库。AI agent 会探索代码，找到相关文件与行范围。

| 参数 | 必需 | 说明 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |

!!! tip "编写具体查询"
    ```python
    # ✅ 好 — 具体且描述性
    agentic_search(query="验证 JWT token 并提取用户 ID 的函数")

    # ❌ 差 — 太模糊
    agentic_search(query="认证逻辑")
    ```

**响应：**

```json
{
  "files": {
    "src/auth/login.py": [[10, 50], [80, 120]],
    "src/middleware/auth.py": [[1, 30]]
  },
  "explanation": "发现的人类可读说明",
  "partial": false
}
```

- **`files`** — 匹配的文件路径 → `[start_line, end_line]` 范围列表
- **`explanation`** — 发现内容的摘要
- **`partial`** — 搜索超时未完成时为 `true`

## 云端工具

!!! info "启用云端工具"
    设置 `RELACE_CLOUD_TOOLS=1` 与 `RELACE_API_KEY`，然后重启 MCP 客户端。

### cloud_sync

上传代码库以进行语义索引。

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `force` | ❌ | `False` | 重新上传所有文件 |
| `mirror` | ❌ | `False` | 删除本地不存在的云端文件 |

!!! warning "镜像模式"
    `cloud_sync(force=True, mirror=True)` 会删除本地不存在的云端文件。谨慎使用。

### cloud_search

对已同步仓库进行语义搜索。

| 参数 | 必需 | 说明 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |
| `branch` | ❌ | 要搜索的分支（空 = API 默认值） |

**响应：**

```json
{
  "results": [
    {
      "filename": "src/middleware/auth.py",
      "score": 0.95,
      "content": "class AuthMiddleware: ..."
    }
  ],
  "result_count": 1
}
```

### cloud_info

获取同步状态和仓库信息。

| 参数 | 必需 | 说明 |
|------|------|------|
| `reason` | ✅ | 检查原因（用于日志） |

### cloud_list

列出 Relace Cloud 账户中的所有仓库。

| 参数 | 必需 | 说明 |
|------|------|------|
| `reason` | ✅ | 检查原因（用于日志） |

### cloud_clear

删除云端仓库和本地同步状态。

!!! danger "不可逆操作"
    这会永久删除云端仓库。无法恢复。

| 参数 | 必需 | 说明 |
|------|------|------|
| `confirm` | ✅ | 必须为 `True` 才能继续 |
| `repo_id` | ❌ | 要删除的特定仓库（默认：当前仓库） |

## agentic_retrieval

两阶段语义 + 智能代码检索。结合云端搜索与本地 agentic 探索，适用于复杂查询。

!!! info "启用"
    设置 `MCP_SEARCH_RETRIEVAL=1` 启用此工具。

| 参数 | 必需 | 说明 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |

## 故障排除

??? question "agentic_search 找不到结果?"

    1. 让查询更具体
    2. 检查代码是否存在于仓库中
    3. 尝试不同措辞
    4. 启用 debug 日志：`MCP_LOG_LEVEL=DEBUG`

??? question "云端同步失败?"

    1. 检查 API key 是否设置
    2. 验证网络连接
    3. 检查仓库是否为 git 仓库
    4. 启用 debug 日志：`MCP_LOG_LEVEL=DEBUG`

??? question "云端工具无法使用?"

    1. 设置 `RELACE_CLOUD_TOOLS=1`
    2. 设置 `RELACE_API_KEY`
    3. 重启 MCP 客户端

??? question "搜索性能缓慢?"

    1. 安装 `ripgrep` 以加速文件扫描
    2. 让查询更具体
    3. 检查系统资源
