# 工具参考

本文档提供所有可用 MCP 工具的详细信息。

## `fast_apply`

对文件应用编辑（或创建新文件）。使用 `// ... existing code ...` 或 `# ... existing code ...` 等截断占位符。

注意：
- 对既有文件编辑时，必须包含 1-2 行从目标文件原文复制的 anchor lines（位于改动附近）。
- truncation markers 更适合较大范围的 scoped edit，但 anchor-only edit 仍然支持。
- 对 `.md` / `.mdx` 目标文件会保留外层 markdown fences，以便原样插入 fenced code block。
- 创建新文件时，请提供完整文件内容，不要包含 truncation markers。
- 仅靠 omission-style 的 context adjacency 不会再单独触发 `APPLY_NOOP`；`APPLY_NOOP` 现在主要用于 explicit remove directive 或明确新增行却没有产生 diff 的情况。
- omission-style deletion detection 仍属于 `APPLY_SEMANTIC_CHECK=1` 的 opt-in 语义校验；默认不启用，以避免仅靠 context adjacency 带来的额外失败。
- 显式 `// remove X` / `# remove X` directive 可让 deletion-dominant 的大删改绕过 truncation 与 blast-radius guard，而不是直接 hard fail。

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

### 常见错误

- `NEEDS_MORE_CONTEXT`：无法在文件中定位 anchor lines。
- `APPLY_NOOP`：snippet 中包含 explicit remove directive 或原文件不存在的 concrete 新行，但 merge 结果仍与原文件完全一致。
- `MARKER_LEAKAGE`：占位符 marker 泄漏到 merged output（被当成字面文本）。
- `TRUNCATION_DETECTED`：在没有 explicit remove directive 的情况下，merged output 出现异常大幅缩短。
- `BLAST_RADIUS_EXCEEDED`：diff 范围过大，需要拆分成更小的 edits。若是带 explicit remove directive 的 deletion-dominant 大删改，则会绕过此 guard。

---

## `agentic_search`

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

## `index_status`

检查 cloud/local indexing readiness。若本地 backend（Codanna/ChunkHound）的 index 过期或缺失，自动安排后台 reindex 任务。

此工具无参数。

### 返回

- `relace`、`codanna`、`chunkhound` 都会包含 `freshness`：`fresh`、`stale`、`missing` 或 `unknown`
- `relace`、`codanna`、`chunkhound` 都会包含 `hints_usable`：表示在 `prefer-stale` 下 `agentic_retrieval` 是否可以使用该 backend 的 semantic hints
- `codanna` 和 `chunkhound` 包含 `background_refresh_scheduled`：`true` 表示已触发后台 reindex
- 对 local backend 而言，`missing` 也包括仅创建了目录、但尚未生成可用 index artifact 的 bootstrap / empty 目录
- Relace cloud 若过期，`status.recommended_action` 会告知调用 `cloud_sync()`

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
| `branch` | ❌ | 要搜索的分支（null 使用 API 默认分支） |

> **注意：** 内部参数（`score_threshold=0.3`、`token_limit=30000`）不暴露给 LLM。

---

## `cloud_list`

列出 Relace Cloud 账户中的所有仓库。

此工具无参数。返回仓库 ID、名称和索引状态。
用于获取 `cloud_clear` 所需的 `repo_id`；正常搜索/同步流程不需要调用。

---

---

## `cloud_clear`

删除云端仓库和本地同步状态。在切换项目或重大重构后重置时使用。

若 `confirm=false`，会返回 `status="cancelled"` 且不会执行删除。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `confirm` | ✅ | `false` | 必须为 `true` 才能继续（安全保护） |
| `repo_id` | ❌ | `null` | 要直接删除的仓库 UUID（用 `cloud_list` 查找）。省略时删除当前目录对应的仓库。**注意：** 直接 `repo_id` 模式不会清除本地 sync state。 |

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

结合 semantic hints 与 agentic code retrieval 的混合检索。它会先用语义 hints 缩小范围，再回到 live code exploration 做确认。

### 运作方式

1. **阶段 1 — 语义提示**：从配置的 backend 检索相关文件/符号提示
2. **阶段 2 — 智能探索**：利用提示引导本地 grep/view 探索当前 workspace 的 live code

`agentic_retrieval` 不会隐式执行 `cloud_sync`。如果你想在 retrieval 前刷新 cloud index，请显式调用 `cloud_sync`。

### Hint Policy

使用 `MCP_RETRIEVAL_HINT_POLICY` 控制 stale index 的处理方式。

| 值 | 默认 | 行为 |
|----|------|------|
| `prefer-stale` | ✅ | 只要有 stale semantic hints 就先用，再由 live code 做确认 |
| `strict` | — | 只有 backend 处于 fresh 状态时才使用 semantic hints |

### Backend 配置

设置 `MCP_RETRIEVAL_BACKEND` 选择 backend。默认值：`relace`。

| 值 | 依赖 | 说明 |
|----|------|------|
| `auto` | — | 自动检测：优先 Codanna → ChunkHound → Relace |
| `codanna` | `codanna` CLI | 符号级语义搜索（本地，无需 API key） |
| `chunkhound` | `chunkhound` CLI + embedding API key | 代码块级语义搜索（本地） |
| `relace` | `RELACE_API_KEY` | 云端语义搜索 |
| `none` | — | 完全跳过语义提示，改为 agentic-only retrieval |

#### Codanna

符号级索引 — 嵌入函数签名和文档字符串。在实现级查询上精度更高。

```bash
# 安装
curl -fsSL --proto '=https' --tlsv1.2 https://install.codanna.sh | sh
# 或: cargo install codanna --locked
# 或: brew install codanna

# 初始化并索引
cd your-project
codanna init
codanna index src

# 启用
export MCP_RETRIEVAL_BACKEND=codanna
```

> 将 `.codanna/` 和 `.codannaignore` 添加到 `.gitignore`。
>
> 当 Codanna index 处于 stale 状态时，`prefer-stale` 仍会使用它的 hints，并排程 background refresh；`strict` 会跳过 stale Codanna hints。

#### ChunkHound

代码块级索引 — 嵌入原始代码块。需要外部 embedding 服务。

```bash
# 安装
pip install chunkhound

# 索引
cd your-project
chunkhound index

# 启用
export MCP_RETRIEVAL_BACKEND=chunkhound
```

Embedding 服务配置（项目根目录 `.chunkhound.json`）：

```json
{
  "embedding": {
    "provider": "openai",
    "api_key": "sk-xxx",
    "model": "text-embedding-3-small"
  }
}
```

使用本地 Ollama（无需 API key）：

```json
{
  "embedding": {
    "provider": "openai-compatible",
    "base_url": "http://localhost:11434/v1",
    "model": "qwen3-embedding:8b"
  }
}
```

> 将 `.chunkhound/` 和 `.chunkhound.json` 添加到 `.gitignore`。
>
> 当 ChunkHound index 处于 stale 状态时，`prefer-stale` 仍会使用它的 hints，并排程 background refresh；`strict` 会跳过 stale ChunkHound hints。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `query` | ✅ | — | 描述要查找内容的自然语言查询 |

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
  "semantic_hints_used": 5,
  "hint_policy": "prefer-stale",
  "hints_index_freshness": "stale",
  "background_refresh_scheduled": true
}
```
