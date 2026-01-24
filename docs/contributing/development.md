# Development Guide

Contributing to Relace MCP.

## Setup

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR-USERNAME/relace-mcp.git
cd relace-mcp
```

### 2. Install Dependencies

```bash
# Install all dependencies including dev tools
uv sync --all-extras --group dev

# Install pre-commit hooks
uv run pre-commit install
```

### 3. Verify Setup

```bash
# Run tests
uv run pytest

# Run linters
uv run ruff check .

# Type check
uv run basedpyright
```

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feat/your-feature-name
```

### 2. Make Changes

Edit code, add tests, update docs.

### 3. Run Checks

```bash
# Format code
uv run ruff format .

# Lint
uv run ruff check . --fix

# Type check
uv run basedpyright

# Tests
uv run pytest

# Coverage
uv run pytest --cov=relace_mcp --cov-report=html
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: add new feature"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Tests
- `refactor:` Code refactoring
- `chore:` Maintenance

### 5. Push and PR

```bash
git push origin feat/your-feature-name
```

Open a Pull Request on GitHub.

## Project Structure

```
relace-mcp/
├── src/
│   └── relace_mcp/
│       ├── __init__.py
│       ├── server.py         # MCP server
│       ├── tools/            # Tool implementations
│       ├── dashboard/        # Dashboard (Textual)
│       └── utils/            # Utilities
├── tests/
│   ├── test_tools.py
│   └── ...
├── docs/                     # Documentation
├── benchmark/                # Benchmarks
└── pyproject.toml            # Project config
```

## Code Style

### Python

- **Formatter**: Ruff (120 char line length)
- **Linter**: Ruff
- **Type Checker**: Basedpyright
- **Python Version**: 3.11+

### Docstrings

Use Google Style:

```python
def example_function(arg1: str, arg2: int) -> bool:
    """Short description.

    Longer description if needed.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When something is wrong.
    """
    pass
```

## Testing

### Run Tests

```bash
# All tests
uv run pytest

# Specific test
uv run pytest tests/test_tools.py

# With coverage
uv run pytest --cov=relace_mcp
```

### Write Tests

```python
import pytest

def test_example():
    """Test description."""
    assert True

@pytest.mark.asyncio
async def test_async_example():
    """Async test."""
    result = await async_function()
    assert result is not None
```

## Documentation

### Build Docs

```bash
# Install docs dependencies
uv sync --extra dev

# Serve locally
uv run mkdocs serve

# Build static site
uv run mkdocs build
```

### Write Docs

- Use Markdown
- Add code examples
- Include admonitions for warnings/tips
- Link related pages

## Tools

### Dashboard

Run the development dashboard:

```bash
uv run relogs
```

### Benchmark

Run benchmarks:

```bash
cd benchmark
uv run python run_benchmark.py
```

## Pre-commit Hooks

Installed with `uv run pre-commit install`:

- Ruff format
- Ruff lint
- Type check (Basedpyright)
- YAML/JSON validation
- Trailing whitespace
- End-of-file fixer

## Release Process

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Commit: `git commit -m "chore: bump version to X.Y.Z"`
4. Tag: `git tag vX.Y.Z`
5. Push: `git push && git push --tags`
6. GitHub Actions will build and publish to PyPI

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/possible055/relace-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/possible055/relace-mcp/discussions)

## Next Steps

- [Testing Guide](testing.md) - Testing details
