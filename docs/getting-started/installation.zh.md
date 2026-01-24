# 安装

Relace MCP 详细安装指南。

## 系统需求

- **Python**: 3.11 或更高版本
- **uv**: 最新版本 ([安装指南](https://docs.astral.sh/uv/))
- **git**: 任何近期版本
- **ripgrep**（可选）：加快代码搜索速度

## 安装方式

### 方式 1：uv tool（推荐）

最简单的安装方式：

```bash
uv tool install relace-mcp
```

这会在隔离环境中安装 `relace-mcp` 并使其全局可用。

**验证安装：**

```bash
uv tool list
# 应显示：relace-mcp v0.2.5
```

### 方式 2：pip

使用 pip（系统级或虚拟环境）：

```bash
# 系统级（可能需要 sudo）
pip install relace-mcp

# 在虚拟环境中
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install relace-mcp
```

### 方式 3：开发安装

用于开发或贡献：

```bash
# Clone repository
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp

# Install with all development dependencies
uv sync --all-extras --group dev

# Install in editable mode
uv pip install -e .
```

## 可选依赖

### ripgrep

显著提升搜索性能：

=== "macOS"

    ```bash
    brew install ripgrep
    ```

=== "Debian/Ubuntu"

    ```bash
    sudo apt-get install ripgrep
    ```

=== "Fedora"

    ```bash
    sudo dnf install ripgrep
    ```

=== "Windows"

    ```powershell
    choco install ripgrep
    # 或
    scoop install ripgrep
    ```

### 开发工具

用于贡献 Relace MCP：

```bash
# Install all additional dependencies
uv sync --all-extras --group dev

# Only install development tools
uv sync --extra dev --group dev

# Specific additional dependencies
uv sync --extra tools      # Dashboard tools
uv sync --extra benchmark  # Benchmark tools
```

## 升级

### uv tool

```bash
uv tool upgrade relace-mcp
```

### pip

```bash
pip install --upgrade relace-mcp
```

## 解除安装

### uv tool

```bash
uv tool uninstall relace-mcp
```

### pip

```bash
pip uninstall relace-mcp
```

## 故障排除

??? question "找不到 uv？"

    先安装 uv：
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

??? question "Python 版本不符？"

    检查 Python 版本：
    ```bash
    python --version
    ```

    必须为 3.11 或更高版本。从 [python.org](https://www.python.org/downloads/) 安装。

??? question "权限错误？"

    使用 `uv tool install` 代替系统级 `pip install`，或使用虚拟环境。

## 下一步

- [快速开始](quick-start.md) - 5 分钟上手
- [配置](configuration.md) - 设置 MCP 客户端
