# 工具参考

本文档提供所有可用 MCP 工具的详细信息。

## `fast_apply`

对文件应用编辑（或创建新文件）。使用 `// ... existing code ...` 或 `# ... existing code ...` 等截断占位符。

### 参数

| 参数 | 必需 | 描述 |
|------|------|------|
| `path` | ✅ | `RELACE_BASE_DIR` 内的绝对路径 |
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
  "turns_used": 4
}
```

---

## `cloud_sync`

将本地代码库同步到 Relace Cloud 以进行语义搜索。将 `RELACE_BASE_DIR` 中的源文件上传到 Relace Repos。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `force` | ❌ | `false` | 强制完整同步，忽略缓存状态 |
| `mirror` | ❌ | `false` | 配合 `force=True` 使用，完全覆盖云端仓库 |

### 行为

- 遵循 `.gitignore` 模式（可用时使用 `git ls-files`）
- 支持 60+ 种常见源代码文件类型（`.py`、`.js`、`.ts`、`.java` 等）
- 跳过大于 1MB 的文件和常见非源代码目录（`node_modules`、`__pycache__` 等）
- 同步状态存储在 `~/.local/state/relace/sync/`

> 高级同步模式（增量、安全完整、镜像）请参见 [advanced.zh-CN.md](advanced.zh-CN.md#同步模式)。

---

## `cloud_search`

对云端同步的仓库进行语义代码搜索。需要先运行 `cloud_sync`。

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `query` | ✅ | — | 自然语言搜索查询 |
| `branch` | ❌ | `""` | 要搜索的分支（空值使用 API 默认值） |
| `score_threshold` | ❌ | `0.3` | 最低相关性分数（0.0-1.0） |
| `token_limit` | ❌ | `30000` | 返回的最大 token 数 |

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

### 参数

| 参数 | 必需 | 默认值 | 描述 |
|------|------|--------|------|
| `confirm` | ✅ | `false` | 必须为 `true` 才能继续（安全保护） |

### 返回

```json
{
  "deleted": true,
  "repo_id": "uuid",
  "state_cleared": true
}
```
