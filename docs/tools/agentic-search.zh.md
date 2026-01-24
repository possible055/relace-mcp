# Agentic Search

使用 AI agent 进行自然语言代码库探索。

## 概述

`agentic_search` 让你能用自然语言查询搜索代码库。AI agent 会探索代码以找到你需要的内容。

## 基本用法

```python
agentic_search(query="用户认证在哪里处理?")
```

**返回:**

```json
{
  "files": {
    "src/auth/login.py": [[10, 50], [80, 120]],
    "src/middleware/auth.py": [[1, 30]]
  },
  "explanation": "用户认证主要在两个地方处理...",
  "partial": false
}
```

## 查询指南

### ✅ 良好查询

具体且描述性:

```python
# 良好:具体函数行为
agentic_search(query="验证 JWT token 并提取用户 ID 的函数")

# 良好:描述要找什么
agentic_search(query="HTTP 4xx 错误被捕获并转换为用户消息的地方")

# 良好:技术性且精确
agentic_search(query="UserService 类初始化和依赖注入")
```

### ❌ 不良查询

过于模糊或宽泛:

```python
# 不良:太模糊
agentic_search(query="认证逻辑")

# 不良:太宽泛
agentic_search(query="错误处理")

# 不良:不够具体
agentic_search(query="配置")
```

## 高级查询

### 多组件搜索

跨相关组件搜索:

```python
agentic_search(
    query="追踪从 HTTP 端点到数据库查询的完整用户创建请求流程"
)
```

### 实现细节

查找特定实现模式:

```python
agentic_search(
    query="所有在数据库写入后使 Redis 缓存失效的地方"
)
```

### 架构探索

理解系统架构:

```python
agentic_search(
    query="事件总线如何连接发布者与订阅者,包括重试逻辑"
)
```

## 使用案例

### 1. Bug 调查

找出可能出现 bug 的地方:

```python
agentic_search(
    query="验证用户 session token 的地方,包括过期检查"
)
```

### 2. 功能实现

在添加功能前定位相关代码:

```python
agentic_search(
    query="所有处理文件上传的 API 端点,包括验证"
)
```

### 3. 代码审查

找出需要审查的代码:

```python
agentic_search(
    query="直接构造 SQL 查询而不使用参数化的函数"
)
```

### 4. 重构

识别重构目标:

```python
agentic_search(
    query="所有使用已弃用 UserManager 类的地方"
)
```

## 最佳实践

### 保持具体

包含技术术语和模式:

```python
# 与其:"日志"
agentic_search(query="我们记录用户认证失败与错误代码的地方")
```

### 描述行为

专注于代码做什么:

```python
# 与其:"支付代码"
agentic_search(query="处理信用卡支付并处理 Stripe webhook 的函数")
```

### 包含上下文

添加相关上下文以缩小结果:

```python
# 与其:"数据库查询"
agentic_search(query="PostgreSQL 查询联结 users 表与 orders 表用于分析")
```

## 响应格式

### 成功响应

```json
{
  "files": {
    "path/to/file.py": [[start_line, end_line], ...],
    ...
  },
  "explanation": "发现的人类可读说明",
  "partial": false
}
```

### 部分结果

当搜索未完成时:

```json
{
  "files": { ... },
  "explanation": "找到部分结果...",
  "partial": true
}
```

## 性能提示

### 1. 使用具体查询

更具体 = 更快结果:

```python
# 慢
agentic_search(query="配置")

# 快
agentic_search(query="settings.py 中的数据库连接池配置")
```

### 2. 安装 ripgrep

显著加快文件扫描:

```bash
# macOS
brew install ripgrep

# Debian/Ubuntu
sudo apt-get install ripgrep
```

### 3. 限制范围

尽可能搜索特定区域:

```python
agentic_search(
    query="src/middleware 目录中的认证中间件"
)
```

## 工具比较

| 工具 | 速度 | 准确度 | 使用案例 |
|------|------|--------|----------|
| `grep` | ⚡⚡⚡ | 低 | 精确文字匹配 |
| `agentic_search` | ⚡⚡ | 高 | 自然语言 |
| `agentic_retrieval` | ⚡ | 非常高 | 复杂查询 |
| `cloud_search` | ⚡ | 高 | 跨仓库 |

## 范例

### 范例 1:找入口点

```python
agentic_search(
    query="创建 FastAPI app 的主应用程序入口点"
)
```

### 范例 2:追踪依赖

```python
agentic_search(
    query="UserRepository 类的所有导入和使用"
)
```

### 范例 3:安全审计

```python
agentic_search(
    query="处理用户密码的函数,包括哈希和验证"
)
```

## 故障排除

??? question "找不到结果?"

    1. 让查询更具体
    2. 检查代码是否存在于仓库中
    3. 尝试不同措辞
    4. 启用 debug 日志:`RELACE_LOG_LEVEL=DEBUG`

??? question "结果太多?"

    1. 添加更具体的术语
    2. 包含文件/目录上下文
    3. 描述确切需要的行为

??? question "性能缓慢?"

    1. 安装 `ripgrep`
    2. 让查询更具体
    3. 检查系统资源

## 下一步

- [Fast Apply](fast-apply.md) - 应用代码变更
- [Cloud Search](cloud-search.md) - 跨仓库搜索
- [API 参考](../advanced/api-reference.md) - 完整 API 文档
