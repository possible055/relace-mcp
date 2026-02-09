# 开发指南

为 Relace MCP 做贡献。

## 设置

### 1. Fork 和克隆

```bash
git clone https://github.com/YOUR-USERNAME/relace-mcp.git
cd relace-mcp
```

### 2. 安装依赖

```bash
# 安装所有依赖，包括开发工具
uv sync --all-extras --group dev

# 安装 pre-commit hooks
uv run pre-commit install
```

### 3. 验证设置

```bash
# 运行测试
uv run pytest

# 运行 linters
uv run ruff check .

# 类型检查
uv run basedpyright
```

## 开发工作流

### 1. 创建功能分支

```bash
git checkout -b feat/your-feature-name
```

### 2. 进行更改

编辑代码、添加测试、更新文档。

### 3. 运行检查

```bash
# 格式化代码
uv run ruff format .

# Lint
uv run ruff check . --fix

# 类型检查
uv run basedpyright

# 测试
uv run pytest

# 覆盖率
uv run pytest --cov=relace_mcp --cov-report=html
```

### 4. 提交更改

```bash
git add .
git commit -m "feat: add new feature"
```

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档
- `test:` 测试
- `refactor:` 代码重构
- `chore:` 维护

### 5. 推送和 PR

```bash
git push origin feat/your-feature-name
```

在 GitHub 上打开 Pull Request。

## 项目结构

```
relace-mcp/
├── src/
│   └── relace_mcp/
│       ├── __init__.py
│       ├── server.py         # MCP 服务器
│       ├── tools/            # 工具实现
│       ├── dashboard/        # Dashboard (Textual)
│       └── utils/            # 工具函数
├── tests/
│   ├── test_tools.py
│   └── ...
├── docs/                     # 文档
├── benchmark/                # 基准测试
└── pyproject.toml            # 项目配置
```

## 代码风格

### Python

- **格式化工具**：Ruff（120 字符行长度）
- **Linter**：Ruff
- **类型检查器**：Basedpyright
- **Python 版本**：3.11+

### Docstrings

使用 Google 风格：

```python
def example_function(arg1: str, arg2: int) -> bool:
    """简短描述。

    如需要可添加更长的描述。

    Args:
        arg1: arg1 的描述。
        arg2: arg2 的描述。

    Returns:
        返回值的描述。

    Raises:
        ValueError: 当出现问题时。
    """
    pass
```

## 测试

### 运行测试

```bash
# 所有测试
uv run pytest

# 特定测试
uv run pytest tests/test_tools.py

# 带覆盖率
uv run pytest --cov=relace_mcp
```

### 编写测试

```python
import pytest

def test_example():
    """测试描述。"""
    assert True

@pytest.mark.asyncio
async def test_async_example():
    """异步测试。"""
    result = await async_function()
    assert result is not None
```

## 文档

### 构建文档

```bash
# 安装文档依赖
uv sync --extra dev

# 本地预览
uv run mkdocs serve

# 构建静态站点
uv run mkdocs build
```

### 编写文档

- 使用 Markdown
- 添加代码示例
- 使用 admonitions 显示警告/提示
- 链接相关页面

## 工具

### Dashboard

运行开发 dashboard：

```bash
uv run relogs
```

### 基准测试

运行基准测试：

```bash
cd benchmark
uv run python run_benchmark.py
```

## Pre-commit Hooks

通过 `uv run pre-commit install` 安装：

- Ruff format
- Ruff lint
- 类型检查 (Basedpyright)
- YAML/JSON 验证
- 尾随空格
- 文件末尾修复

## 发布流程

1. 更新 `pyproject.toml` 中的版本
2. 更新 `CHANGELOG.md`
3. 提交：`git commit -m "chore: bump version to X.Y.Z"`
4. 打标签：`git tag vX.Y.Z`
5. 推送：`git push && git push --tags`
6. GitHub Actions 将构建并发布到 PyPI

## 获取帮助

- **Issues**：[GitHub Issues](https://github.com/possible055/relace-mcp/issues)
- **讨论**：[GitHub Discussions](https://github.com/possible055/relace-mcp/discussions)

## 下一步

- [测试指南](testing.zh.md) - 测试详情
