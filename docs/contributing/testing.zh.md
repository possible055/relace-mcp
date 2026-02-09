# 测试指南

Relace MCP 的完整测试指南。

## 运行测试

### 所有测试

```bash
uv run pytest
```

### 特定测试文件

```bash
uv run pytest tests/test_tools.py
```

### 特定测试函数

```bash
uv run pytest tests/test_tools.py::test_fast_apply
```

### 带覆盖率

```bash
uv run pytest --cov=relace_mcp --cov-report=html
```

查看覆盖率报告：`open htmlcov/index.html`

## 测试结构

```
tests/
├── conftest.py           # 共享 fixtures
├── smoke/                # 基础启动测试（CI 门禁）
├── unit/                 # 单元测试（快速，无外部依赖）
├── integration/          # 集成测试（Server + Client）
└── contract/             # MCP 协议合规测试 ⭐
```

## MCP 健康检查（发布前门禁）

在推送到 PyPI 之前，运行合约测试以验证 MCP 功能完整：

```bash
# 快速健康检查（约 3 秒）
uv run pytest tests/contract/ -v

# 仅完整健康检查
uv run pytest tests/contract/test_health_indicators.py::TestFullHealthCheck -v
```

### 健康检查指标

| 指标 | 描述 |
|------|------|
| `server_builds` | 服务器可以使用有效配置构建 |
| `tools_registered` | 核心工具已注册 |
| `schemas_valid` | 工具 schema 包含必需字段 |
| `tool_callable` | 工具可以调用而不崩溃 |
| `response_format` | 工具响应遵循预期格式 |

### 合约测试覆盖

- **核心工具**：`fast_apply`、`agentic_search`
- **云工具**：`cloud_sync`、`cloud_search`、`cloud_clear`、`cloud_list`、`cloud_info`
- **Schema 验证**：所有工具参数和类型
- **MCP 注解**：`readOnlyHint`、`destructiveHint` 等
- **响应合约**：状态码、错误格式

## 编写测试

### 基础测试

```python
def test_example():
    """测试描述。"""
    result = function_to_test()
    assert result == expected_value
```

### 异步测试

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """测试异步函数。"""
    result = await async_function()
    assert result is not None
```

### 参数化测试

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("test", "TEST"),
    ("hello", "HELLO"),
])
def test_uppercase(input, expected):
    """测试大写转换。"""
    assert input.upper() == expected
```

### Fixtures

```python
import pytest

@pytest.fixture
def sample_data():
    """提供示例数据。"""
    return {"key": "value"}

def test_with_fixture(sample_data):
    """使用 fixture 的测试。"""
    assert sample_data["key"] == "value"
```

## 测试工具

### Fast Apply

```python
@pytest.mark.asyncio
async def test_fast_apply():
    """测试 fast_apply 工具。"""
    result = await fast_apply(
        path="test.py",
        edit_snippet="def test(): pass",
        instruction="Add function"
    )
    assert result["status"] == "ok"
```

### Agentic Search

```python
@pytest.mark.asyncio
async def test_agentic_search():
    """测试 agentic_search 工具。"""
    result = await agentic_search(
        query="test function"
    )
    assert "files" in result
    assert isinstance(result["files"], dict)
```

### 云工具

```python
@pytest.mark.asyncio
async def test_cloud_sync(mock_api):
    """使用模拟 API 测试 cloud_sync。"""
    result = await cloud_sync(force=False)
    assert result["status"] == "synced"
```

## Mock

### Mock 外部 API

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    """使用模拟 API 的测试。"""
    with patch('relace_mcp.client.RelaceClient.apply') as mock_apply:
        mock_apply.return_value = {"status": "ok"}

        result = await fast_apply(
            path="test.py",
            edit_snippet="code"
        )

        assert result["status"] == "ok"
        mock_apply.assert_called_once()
```

### Mock 环境变量

```python
import os
from unittest.mock import patch

def test_with_env_var():
    """使用环境变量的测试。"""
    with patch.dict(os.environ, {"RELACE_API_KEY": "test-key"}):
        # 测试代码
        assert os.getenv("RELACE_API_KEY") == "test-key"
```

## 测试覆盖率

### 目标覆盖率

- **最低**：80% 整体
- **关键路径**：95%+
- **工具实现**：90%+

### 检查覆盖率

```bash
# 生成覆盖率报告
uv run pytest --cov=relace_mcp --cov-report=term-missing

# HTML 报告
uv run pytest --cov=relace_mcp --cov-report=html
open htmlcov/index.html
```

### 排除覆盖率

添加到 `pyproject.toml`：

```toml
[tool.coverage.run]
omit = [
    "tests/*",
    "*/dashboard/*",  # UI 代码
]
```

## 集成测试

### 设置测试仓库

```python
import tempfile
import shutil

@pytest.fixture
def test_repo():
    """创建临时测试仓库。"""
    repo_dir = tempfile.mkdtemp()
    # 设置测试文件
    yield repo_dir
    # 清理
    shutil.rmtree(repo_dir)
```

### 使用真实文件测试

```python
def test_with_real_files(test_repo):
    """使用真实文件系统测试。"""
    test_file = test_repo / "test.py"
    test_file.write_text("def example(): pass")

    result = process_file(test_file)
    assert result is not None
```

## 性能测试

### 基准测试

```python
import time

def test_performance():
    """测试性能要求。"""
    start = time.time()

    result = expensive_operation()

    duration = time.time() - start
    assert duration < 1.0  # 必须在 1 秒内完成
    assert result is not None
```

### 负载测试

```python
import asyncio

@pytest.mark.asyncio
async def test_concurrent_requests():
    """测试并发请求处理。"""
    tasks = [
        async_operation(i)
        for i in range(100)
    ]

    results = await asyncio.gather(*tasks)
    assert len(results) == 100
```

## 调试测试

### 带调试输出运行

```bash
uv run pytest -v -s
```

### 失败时进入调试器

```bash
uv run pytest --pdb
```

### 使用 breakpoint()

```python
def test_with_breakpoint():
    """带断点的测试。"""
    result = function()
    breakpoint()  # 进入 pdb
    assert result == expected
```

## CI/CD 测试

GitHub Actions 运行：

1. Linting (Ruff)
2. 类型检查 (Basedpyright)
3. 单元测试
4. 集成测试
5. 覆盖率报告

配置见 `.github/workflows/test.yml`。

## 最佳实践

### 1. 测试一件事

```python
# 好
def test_addition():
    assert add(2, 2) == 4

# 不好 - 测试多件事
def test_everything():
    assert add(2, 2) == 4
    assert subtract(5, 3) == 2
    assert multiply(3, 4) == 12
```

### 2. 使用描述性名称

```python
# 好
def test_user_login_with_invalid_password_returns_error():
    pass

# 不好
def test_login():
    pass
```

### 3. Arrange-Act-Assert

```python
def test_example():
    # Arrange（准备）
    user = User("test")

    # Act（执行）
    result = user.login("password")

    # Assert（断言）
    assert result is True
```

### 4. 测试边界情况

```python
@pytest.mark.parametrize("value", [
    0,           # 零
    -1,          # 负数
    999999,      # 大数
    None,        # 空值
    "",          # 空字符串
])
def test_edge_cases(value):
    """测试边界情况。"""
    result = handle_value(value)
    assert result is not None
```

## 故障排除

??? question "测试挂起？"

    - 添加超时：`@pytest.mark.timeout(5)`
    - 检查异步代码中的死锁
    - 使用 `pytest -v` 获取详细输出

??? question "测试不稳定？"

    - 添加重试：`@pytest.mark.flaky(reruns=3)`
    - 修复时序问题
    - Mock 外部依赖

??? question "覆盖率太低？"

    - 为未测试的代码添加测试
    - 删除死代码
    - 测试错误路径

## 下一步

- [开发指南](development.zh.md) - 开发工作流
