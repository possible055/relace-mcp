# 工具参考

本文档提供所有可用 MCP 工具的详细信息。

## `fast_apply`

对文件应用编辑（或创建新文件）。使用 `// ... existing code ...` 或 `# ... existing code ...` 等截断占位符。

### 参数

| 参数 | 必需 | 描述 |
|------|------|------|
| `path` | ✅ | `MCP_BASE_DIR` 内的路径（绝对或相对） |
| `edit_snippet` | ✅ | 带有缩写占位符的代码 |
| `instruction` | ❌ | 消歧提示 |

### 示例

```json
{
  "path": "/home/user/project/src/file.py",
  "edit_snippet": "// ... existing code ...\nfunction newFeature() {}\n// ... existing code ...",
  "instruction": "Add new feature"
}
```

### 返回

更改的 UDiff，或新文件的确认信息。

---

## `fast_search`

搜索代码库并返回相关文件和行范围。使用智能循环自主探索代码库。

### 行为

- 长任务期间会周期性发送 progress 通知。
- 达到 `SEARCH_MAX_TURNS` 或 `SEARCH_TIMEOUT_SECONDS` 时，可能返回 `partial=true`（并可选带 `error`）。

### 参数

| 参数 | 必需 | 描述 |
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

## `cloud_sync`

> **注意：** 所有 `cloud_*` 工具的响应都会包含 `trace_id`。失败时响应还可能包含 `status_code`、`error_code`、`retryable`、`recommended_action`。

将本地代码库同步到 Relace Cloud 以进行语义搜索。将 `MCP_BASE_DIR` 中的源文件上传到 Relace Repos。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `force` | ❌ | `false` | 强制完整同步，忽略缓存状态 |
| `mirror` | ❌ | `false` | 配合 `force=True` 使用，完全覆盖云端仓库 |

### 行为

- 遵循 `.gitignore` 模式（可用时使用 `git ls-files`）
- 支持 60+ 种常见源代码文件类型（`.py`、`.js`、`.ts`、`.java` 等）
- 跳过大于 1MB 的文件和常见非源代码目录（`node_modules`、`__pycache__` 等）
- 同步状态存储在平台 state 目录中（例如 Linux 为 `~/.local/state/relace/sync/`），按 repo 名称 + fingerprint 进行区分

> 高级同步模式（增量、安全完整、镜像）请参见 [advanced.zh-CN.md](advanced.zh-CN.md#同步模式)。

---

## `cloud_search`

对云端同步的仓库进行语义代码搜索。需要先运行 `cloud_sync`。

### 参数

| 参数 | 必需 | 描述 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |
| `branch` | ❌ | 要搜索的分支（空值使用 API 默认值） |

> **注意：** 内部参数（`score_threshold=0.3`、`token_limit=30000`）不暴露给 LLM。

---

## `cloud_list`

列出 Relace Cloud 账户中的所有仓库。

### 参数

无

---

## `cloud_info`

获取当前仓库的详细同步状态。在 `cloud_sync` 之前使用以了解需要执行的操作。

### 参数

无

---

## `cloud_clear`

删除云端仓库和本地同步状态。在切换项目或重大重构后重置时使用。

若 `confirm=false`，会返回 `status="cancelled"` 且不会执行删除。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `confirm` | ✅ | `false` | 必须为 `true` 才能继续（安全保护） |

### 返回

```json
{
  "trace_id": "a1b2c3d4",
  "status": "deleted",
  "message": "Repository 'example' (uuid) and local sync state deleted successfully.",
  "repo_name": "example",
  "cloud_repo_name": "example__fingerprint",
  "repo_id": "uuid"
}
```

---

## `agentic_retrieval`

两阶段语义 + 智能代码检索。结合云端语义搜索与本地智能探索以获取精确结果。

### 行为

1. **阶段 1**：运行 `cloud_search` 获取语义相关的候选文件
2. **阶段 2**：将候选文件作为提示引导智能探索（grep、view 等）

若云端不可用则回退到纯智能搜索。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `query` | ✅ | — | 描述要查找内容的自然语言查询 |
| `branch` | ❌ | `""` | 要搜索的分支（空值使用 API 默认值） |
| `score_threshold` | ❌ | `0.3` | 提示文件的最低相关性分数（0.0-1.0） |
| `max_hints` | ❌ | `8` | 使用的最大提示文件数 |

### 响应示例

```json
{
  "query": "用户认证是如何处理的？",
  "explanation": "认证逻辑在 src/auth/...",
  "files": {
    "/home/user/project/src/auth/login.py": [[10, 80]]
  },
  "turns_used": 3,
  "partial": false,
  "trace_id": "a1b2c3d4",
  "cloud_hints_used": 5
}
```
