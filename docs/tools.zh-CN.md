# 工具参考

请使用 `list_tools()` 和 `list_resources()` 查看当前会话中可用的内容。

## `fast_apply`

对文件应用编辑，或创建新文件。

### 注意事项

- 编辑已有文件时，请在改动附近包含 1-2 行从目标文件原文复制的 anchor lines。
- 创建新文件时，请提供完整文件内容。
- 较大范围的编辑可使用 `// ... existing code ...` 与 `# ... existing code ...` 这类截断占位符。

### 参数

| 参数 | 必需 | 描述 |
|------|------|------|
| `path` | ✅ | 绝对路径，或相对于 `MCP_BASE_DIR` 的路径。若未设置 `MCP_BASE_DIR`，相对路径会按当前 MCP root 解析。 |
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

返回结构化对象。成功时可查看 `diff` 了解实际变更。

### 常见错误

- `NEEDS_MORE_CONTEXT`：无法在文件中定位 anchor lines。
- `APPLY_NOOP`：这次编辑没有产生文件变更。
- `MARKER_LEAKAGE`：占位符 marker 泄漏到合并结果中。
- `TRUNCATION_DETECTED`：在没有显式删除指令时，合并结果异常缩短。
- `BLAST_RADIUS_EXCEEDED`：变更范围过大，需要拆分成更小的 edits。

---

## `agentic_search`

搜索代码库并返回相关文件和行范围。

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

## `index_status`

仅在 `MCP_RETRIEVAL_BACKEND` 为 `relace`、`codanna` 或 `chunkhound` 时可用。

以只读方式检查当前唯一 active backend 的索引状态。

此工具不接受参数。

适合在 retrieval 前先判断当前 backend 是否够新，以及 semantic hints 是否可用。

返回 `active_backend`、单一的 `backend` 状态对象（包含 `freshness`、`hints_usable`），以及 `background_monitor` 摘要（`state`、`reason`，以及 `last_status` / `last_error` / `failure_count` — `failure_count` 非零表示 monitor 已进入指数退避）。

此工具不会主动刷新 index。若 `active_backend` 是 `relace` 且 `backend.status.needs_sync` 为 `true`，请运行 `cloud_sync()`。

---

## `cloud_sync`

仅在 `MCP_RETRIEVAL_BACKEND=relace` 时可用。

将本地代码库同步到 Relace Cloud 以进行语义搜索。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `force` | ❌ | `false` | 强制完整同步，忽略缓存状态 |
| `mirror` | ❌ | `false` | 配合 `force=True` 使用，完全覆盖云端仓库 |

> 同步模式（增量、安全完整、镜像）请参见 [advanced.zh-CN.md](advanced.zh-CN.md#同步模式)。

---

## `cloud_search`

仅在 `MCP_RETRIEVAL_BACKEND=relace` 时可用。

对云端同步的仓库进行语义代码搜索。需要先运行 `cloud_sync`。

### 参数

| 参数 | 必需 | 描述 |
|------|------|------|
| `query` | ✅ | 自然语言搜索查询 |
| `branch` | ❌ | 要搜索的分支（`null` 使用 API 默认分支） |

---

## `cloud_list`

仅在 `MCP_RETRIEVAL_BACKEND=relace` 时可用。

列出 Relace Cloud 账户中的仓库。可用它获取 `cloud_clear` 所需的 `repo_id`。

此工具无参数。

---

## `cloud_clear`

仅在 `MCP_RETRIEVAL_BACKEND=relace` 时可用。

删除云端仓库和本地同步状态。

若 `confirm=false`，会返回 `status="cancelled"` 且不会执行删除。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `confirm` | ✅ | `false` | 必须为 `true` 才能继续 |
| `repo_id` | ❌ | `null` | 要直接删除的仓库 UUID。省略时删除当前目录对应的仓库。 |

---

## `agentic_retrieval`

仅在 `MCP_SEARCH_RETRIEVAL=1` 时可用。

结合 semantic hints 与代码检索。它会先用语义 hints 缩小范围，再回到 live code exploration 做确认。

`agentic_retrieval` 不会隐式执行 `cloud_sync`。如果你想在 retrieval 前刷新 cloud index，请显式调用 `cloud_sync`。

### Hint Policy

使用 `MCP_RETRIEVAL_HINT_POLICY` 控制 stale index 的处理方式。

| 值 | 默认 | 行为 |
|----|------|------|
| `prefer-stale` | ✅ | 只要有可用的 stale semantic hints 就先使用，再由 live code 做确认 |
| `strict` | — | 只有所选 backend 处于 fresh 状态时才使用 semantic hints |

### Backend 配置

设置 `MCP_RETRIEVAL_BACKEND` 选择 backend。默认值：`relace`。

| 值 | 依赖 | 说明 |
|----|------|------|
| `codanna` | `codanna` CLI | 符号级语义搜索（本地） |
| `chunkhound` | `chunkhound` CLI + embedding API key | 代码块级语义搜索（本地） |
| `relace` | `RELACE_API_KEY` | 云端语义搜索 |
| `none` | — | 完全跳过语义提示，改为 agentic-only retrieval |

backend 的安装与配置请参见 [advanced.zh-CN.md](advanced.zh-CN.md#本地检索后端)。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `query` | ✅ | — | 描述要查找内容的自然语言查询 |

### 响应示例

```json
{
  "query": "How is user authentication handled?",
  "explanation": "Auth logic is in src/auth/...",
  "files": {
    "/home/user/project/src/auth/login.py": [[10, 80]]
  },
  "turns_used": 3,
  "partial": false
}
```
