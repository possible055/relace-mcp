# Cloud Search

对云端同步仓库进行语义搜索。

## 概述

Cloud Search 支持对同步到 Relace Cloud 的单个仓库进行语义代码搜索。

该工具会基于当前 base dir（通过 `MCP_BASE_DIR` 或 MCP Roots）推导要操作的仓库。

## 前置需求

1. **启用云端工具**:设置 `RELACE_CLOUD_TOOLS=1`
2. **API key**:设置 `RELACE_API_KEY`
3. **重启**:重启 MCP 客户端

## 快速开始

### 1. 同步仓库

首先同步代码库到云端:

```python
cloud_sync(force=False, mirror=False)
```

**返回:**

```json
{
  "trace_id": "a1b2c3d4",
  "repo_id": "r_...",
  "repo_head": "abc123...",
  "sync_mode": "incremental",
  "files_created": 42,
  "files_updated": 0,
  "files_deleted": 0,
  "files_skipped": 108,
  "warnings": []
}
```

### 2. 搜索仓库

使用自然语言搜索:

```python
cloud_search(query="认证中间件")
```

**返回:**

```json
{
  "trace_id": "a1b2c3d4",
  "query": "认证中间件",
  "branch": "",
  "hash": "abc123...",
  "repo_id": "r_...",
  "result_count": 1,
  "results": [
    {
      "filename": "src/middleware/auth.py",
      "score": 0.95,
      "content": "class AuthMiddleware: ..."
    }
  ],
  "warnings": []
}
```

## 云端工具

### cloud_sync

上传代码库以进行语义索引。

**参数:**

- `force` (bool):重新上传所有文件(默认:`False`)
- `mirror` (bool):删除本地不存在的云端文件(默认:`False`)

**范例:**

```python
# 增量同步(默认)
cloud_sync()

# 强制完整重新同步
cloud_sync(force=True)

# 镜像模式(危险!)
cloud_sync(force=True, mirror=True)
```

### cloud_search

搜索已同步仓库。

**参数:**

- `query` (str):自然语言搜索查询
- `branch` (str,可选):要搜索的分支(空字符串使用 API 默认值)

**范例:**

```python
# 基本搜索
cloud_search(query="用户认证")

# 具体搜索
cloud_search(query="中间件中的 JWT token 验证")

# 跨切面关注点
cloud_search(query="数据库超时的错误处理")
```

### cloud_info

获取同步状态和仓库信息。

**参数:**

- `reason` (str):检查原因(用于日志)

**范例:**

```python
cloud_info(reason="搜索前检查同步状态")
```

**返回:**

```json
{
  "trace_id": "a1b2c3d4",
  "repo_name": "my-repo",
  "cloud_repo_name": "my-repo__fp",
  "local": { "git_branch": "main", "git_head": "abc12345", "git_dirty": false },
  "synced": { "repo_id": "r_...", "repo_head": "abc12345", "tracked_files": 150 },
  "cloud": { "repo_id": "r_...", "name": "my-repo__fp", "auto_index": true },
  "status": { "needs_sync": false, "ref_changed": false, "recommended_action": null },
  "warnings": []
}
```

### cloud_list

列出 Relace Cloud 账户中的所有仓库。

**范例:**

```python
cloud_list(reason="检查可用仓库")
```

**返回:**

```json
{
  "trace_id": "a1b2c3d4",
  "count": 2,
  "repos": [
    { "repo_id": "r_...", "name": "my-repo", "auto_index": true },
    { "repo_id": "r_...", "name": "another-repo", "auto_index": false }
  ],
  "has_more": false
}
```

### cloud_clear

删除云端仓库和本地同步状态。

!!! danger "不可逆操作"
    这会永久删除云端仓库。无法恢复。

**参数:**

- `confirm` (bool):必须为 `True` 才能继续
- `repo_id` (str,可选):要删除的特定仓库

**范例:**

```python
# 删除当前仓库
cloud_clear(confirm=True)

# 删除特定仓库
cloud_clear(confirm=True, repo_id="r_...")
```

## 同步模式

### 增量同步(默认)

仅上传新增/变更文件:

```python
cloud_sync()
```

- 快速
- 高效
- 建议日常使用

### 强制同步

重新上传所有文件:

```python
cloud_sync(force=True)
```

- 较慢
- 用于重大变更后
- 重建整个索引

### 镜像同步

删除本地不存在的云端文件:

```python
cloud_sync(force=True, mirror=True)
```

!!! warning "谨慎使用"
    镜像模式会删除本地不存在的云端文件。仅在确定时使用。

## 最佳实践

### 1. 搜索前同步

搜索前总是同步:

```python
# 检查同步状态
cloud_info(reason="搜索前")

# 需要时同步
cloud_sync()

# 现在搜索
cloud_search(query="...")
```

### 2. 增量同步

开发期间增量同步:

```python
# 进行变更后
cloud_sync()  # 快速,仅上传变更
```

### 3. 监控同步状态

定期检查同步状态:

```python
info = cloud_info(reason="每日检查")
if info["status"]["needs_sync"]:
    cloud_sync()
```

## 使用案例

### 多仓库项目

跨相关仓库搜索（需要对每个仓库分别同步与搜索）:

```python
# 在每个仓库中:
cloud_sync()
cloud_search(query="共享认证逻辑")
```

### 代码重用

跨项目查找可重用代码:

```python
cloud_search(query="指数退避的重试装饰器")
```

### 架构审查

理解跨代码库的模式:

```python
cloud_search(query="数据库迁移脚本")
```

## 性能

性能取决于文件数量、网络状况与 Relace Cloud 负载。初次同步通常明显慢于后续的增量同步。

## 故障排除

??? question "同步失败?"

    1. 检查 API key 是否设置
    2. 验证网络连接
    3. 检查仓库是否为 git 仓库
    4. 启用 debug 日志:`MCP_LOG_LEVEL=DEBUG`

??? question "搜索找不到结果?"

    1. 确保仓库已同步
    2. 尝试更宽泛的查询
    3. 用 `cloud_info` 检查同步状态
    4. 用 `cloud_sync(force=True)` 重新同步

??? question "工具无法使用?"

    1. 设置 `RELACE_CLOUD_TOOLS=1`
    2. 设置 `RELACE_API_KEY`
    3. 重启 MCP 客户端

## 下一步

- [Agentic Search](agentic-search.md) - 本地搜索
- [Fast Apply](fast-apply.md) - 应用变更
- [配置](../configuration/overview.md) - 高级配置
