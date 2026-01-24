# 工具参考

本文档描述 Relace MCP 暴露的 MCP tool schema。

## 约定

- `path` 可以是绝对路径，或相对 `MCP_BASE_DIR` 的相对路径。
- `edit_snippet` 支持截断占位符，如 `// ... existing code ...`、`# ... existing code ...`。

---

## `fast_apply`

对文件应用编辑（或创建新文件）。

### 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `path` | ✅ | 文件路径（绝对或相对 `MCP_BASE_DIR`） |
| `edit_snippet` | ✅ | 带截断占位符的代码片段 |
| `instruction` | ❌ | 消歧提示 |

### 返回

更改的 UDiff，或新文件的确认信息。

---

## `agentic_search`

搜索代码库并返回相关文件和行范围。

### 行为

- 长任务期间会周期性发送 progress 通知。
- 达到 `SEARCH_MAX_TURNS` 或 `SEARCH_TIMEOUT_SECONDS` 时，可能返回 `partial=true`（并可选带 `error`）。

### 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |

### 响应示例

```json
{
  "query": "How is authentication implemented?",
  "explanation": "Auth logic is in src/auth/...",
  "files": {
    "/home/user/project/src/auth/login.py": [[10, 80]]
  },
  "turns_used": 4,
  "partial": false
}
```

---

## `agentic_retrieval`

两阶段语义 + 智能代码检索。

### 行为

1. **阶段 1**：根据 `MCP_RETRIEVAL_BACKEND` 加载语义提示
   - `relace`：使用 `cloud_search`（需要启用 cloud tools）
   - `chunkhound`：本地语义搜索（需单独安装：`pip install chunkhound`）
   - `codanna`：本地 codanna 索引
   - `none`：跳过提示
2. **阶段 2**：使用提示引导 agentic exploration。

### 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `query` | ✅ | 描述要查找内容的自然语言查询 |

---

## 云端工具

!!! info "启用云端工具"
    设置 `RELACE_CLOUD_TOOLS=1` 启用 `cloud_*` 工具。启用云端工具时必须设置 `RELACE_API_KEY`。

> **注意：** 所有 `cloud_*` 工具的响应都会包含 `trace_id`。失败时响应还可能包含 `status_code`、`error_code`、`retryable`、`recommended_action`。

## `cloud_sync`

将本地代码库同步到 Relace Cloud 以进行语义搜索。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `force` | ❌ | `false` | 强制完整同步，忽略缓存状态 |
| `mirror` | ❌ | `false` | 配合 `force=True` 使用，删除本地不存在的云端文件 |

---

## `cloud_search`

对云端同步的仓库进行语义代码搜索。需要先运行 `cloud_sync`。

### 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |
| `branch` | ❌ | 要搜索的分支（空值使用 API 默认值） |

---

## `cloud_list`

列出 Relace Cloud 账户中的所有仓库。

### 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `reason` | ❌ | LLM 链式思维的简要说明（工具会忽略） |

---

## `cloud_info`

获取当前仓库的详细同步状态。在 `cloud_sync` 之前使用以了解需要执行的操作。

### 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `reason` | ❌ | LLM 链式思维的简要说明（工具会忽略） |

---

## `cloud_clear`

删除云端仓库和本地同步状态。在切换项目或重大重构后重置时使用。

若 `confirm=false`，会返回 `status="cancelled"` 且不会执行删除。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `confirm` | ✅ | `false` | 必须为 `true` 才能继续（安全保护） |
| `repo_id` | ❌ | — | 可选：直接删除指定 repo |
