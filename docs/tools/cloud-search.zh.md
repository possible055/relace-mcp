# Cloud Search

跨云端同步仓库的语义搜索。

## 概述

Cloud Search 支持对同步到 Relace Cloud 的多个仓库进行语义代码搜索。适合 monorepo 项目或跨相关代码库搜索。

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
  "status": "synced",
  "files_uploaded": 42,
  "files_skipped": 108
}
```

### 2. 跨仓库搜索

使用自然语言搜索:

```python
cloud_search(query="认证中间件")
```

**返回:**

```json
{
  "results": [
    {
      "file": "src/middleware/auth.py",
      "score": 0.95,
      "snippet": "class AuthMiddleware...",
      "line_range": [10, 30]
    }
  ]
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
  "local": {
    "branch": "main",
    "commit": "abc123..."
  },
  "synced": {
    "ref": "main@abc123",
    "files": 150
  },
  "cloud": {
    "repo_id": "r_...",
    "name": "my-repo"
  },
  "status": "synced"
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
[
  {
    "repo_id": "r_...",
    "name": "my-repo",
    "auto_index": true
  },
  {
    "repo_id": "r_...",
    "name": "another-repo",
    "auto_index": false
  }
]
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
if info["status"] != "synced":
    cloud_sync()
```

## 使用案例

### 多仓库项目

跨相关仓库搜索:

```python
# 同步所有仓库
# (切换到每个仓库并执行 cloud_sync)

# 搜索所有仓库
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

### 同步速度

| 仓库大小 | 初次同步 | 增量 |
|---------|---------|------|
| 小(< 100 文件) | ~10s | ~1s |
| 中(< 1000 文件) | ~1min | ~5s |
| 大(< 10000 文件) | ~10min | ~30s |

### 搜索速度

典型搜索延迟:

- **简单查询**:100-500ms
- **复杂查询**:500ms-2s
- **跨仓库**:1-5s

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
- [配置](../setup/configuration.md) - 高级配置
