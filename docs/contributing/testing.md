# Testing Guide

Comprehensive testing guide for Relace MCP.

## Running Tests

### All Tests

```bash
uv run pytest
```

### Specific Test File

```bash
uv run pytest tests/test_tools.py
```

### Specific Test Function

```bash
uv run pytest tests/test_tools.py::test_fast_apply
```

### With Coverage

```bash
uv run pytest --cov=relace_mcp --cov-report=html
```

View coverage report: `open htmlcov/index.html`

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── smoke/                # Basic startup tests (CI gate)
├── unit/                 # Unit tests (fast, no external deps)
├── integration/          # Integration tests (Server + Client)
└── contract/             # MCP protocol compliance tests ⭐
```

## MCP Health Check (Pre-release Gate)

Before pushing to PyPI, run the contract tests to verify MCP is fully functional:

```bash
# Quick health check (~3 seconds)
uv run pytest tests/contract/ -v

# Full health check only
uv run pytest tests/contract/test_health_indicators.py::TestFullHealthCheck -v
```

### Health Check Indicators

| Indicator | Description |
|-----------|-------------|
| `server_builds` | Server can be built with valid config |
| `tools_registered` | Core tools are registered |
| `schemas_valid` | Tool schemas have required fields |
| `tool_callable` | Tools can be invoked without crash |
| `response_format` | Tool responses follow expected format |

### Contract Tests Coverage

- **Core Tools**: `fast_apply`, `agentic_search`
- **Cloud Tools**: `cloud_sync`, `cloud_search`, `cloud_clear`, `cloud_list`, `cloud_info`
- **Schema Validation**: All tool parameters and types
- **MCP Annotations**: `readOnlyHint`, `destructiveHint`, etc.
- **Response Contracts**: Status codes, error formats

## Writing Tests

### Basic Test

```python
def test_example():
    """Test description."""
    result = function_to_test()
    assert result == expected_value
```

### Async Test

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None
```

### Parameterized Tests

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("test", "TEST"),
    ("hello", "HELLO"),
])
def test_uppercase(input, expected):
    """Test uppercase conversion."""
    assert input.upper() == expected
```

### Fixtures

```python
import pytest

@pytest.fixture
def sample_data():
    """Provide sample data."""
    return {"key": "value"}

def test_with_fixture(sample_data):
    """Test using fixture."""
    assert sample_data["key"] == "value"
```

## Testing Tools

### Fast Apply

```python
@pytest.mark.asyncio
async def test_fast_apply():
    """Test fast_apply tool."""
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
    """Test agentic_search tool."""
    result = await agentic_search(
        query="test function"
    )
    assert "files" in result
    assert isinstance(result["files"], dict)
```

### Cloud Tools

```python
@pytest.mark.asyncio
async def test_cloud_sync(mock_api):
    """Test cloud_sync with mocked API."""
    result = await cloud_sync(force=False)
    assert result["status"] == "synced"
```

## Mocking

### Mock External APIs

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    """Test with mocked API."""
    with patch('relace_mcp.client.RelaceClient.apply') as mock_apply:
        mock_apply.return_value = {"status": "ok"}

        result = await fast_apply(
            path="test.py",
            edit_snippet="code"
        )

        assert result["status"] == "ok"
        mock_apply.assert_called_once()
```

### Mock Environment Variables

```python
import os
from unittest.mock import patch

def test_with_env_var():
    """Test with environment variable."""
    with patch.dict(os.environ, {"RELACE_API_KEY": "test-key"}):
        # Test code here
        assert os.getenv("RELACE_API_KEY") == "test-key"
```

## Test Coverage

### Target Coverage

- **Minimum**: 80% overall
- **Critical paths**: 95%+
- **Tool implementations**: 90%+

### Check Coverage

```bash
# Generate coverage report
uv run pytest --cov=relace_mcp --cov-report=term-missing

# HTML report
uv run pytest --cov=relace_mcp --cov-report=html
open htmlcov/index.html
```

### Exclude from Coverage

Add to `pyproject.toml`:

```toml
[tool.coverage.run]
omit = [
    "tests/*",
    "*/dashboard/*",  # UI code
]
```

## Integration Tests

### Setup Test Repository

```python
import tempfile
import shutil

@pytest.fixture
def test_repo():
    """Create temporary test repository."""
    repo_dir = tempfile.mkdtemp()
    # Setup test files
    yield repo_dir
    # Cleanup
    shutil.rmtree(repo_dir)
```

### Test with Real Files

```python
def test_with_real_files(test_repo):
    """Test with real file system."""
    test_file = test_repo / "test.py"
    test_file.write_text("def example(): pass")

    result = process_file(test_file)
    assert result is not None
```

## Performance Tests

### Benchmark Tests

```python
import time

def test_performance():
    """Test performance requirement."""
    start = time.time()

    result = expensive_operation()

    duration = time.time() - start
    assert duration < 1.0  # Must complete in < 1 second
    assert result is not None
```

### Load Tests

```python
import asyncio

@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test concurrent request handling."""
    tasks = [
        async_operation(i)
        for i in range(100)
    ]

    results = await asyncio.gather(*tasks)
    assert len(results) == 100
```

## Debugging Tests

### Run with Debug Output

```bash
uv run pytest -v -s
```

### Drop into debugger on failure

```bash
uv run pytest --pdb
```

### Use breakpoint()

```python
def test_with_breakpoint():
    """Test with breakpoint."""
    result = function()
    breakpoint()  # Drops into pdb
    assert result == expected
```

## CI/CD Testing

GitHub Actions runs:

1. Linting (Ruff)
2. Type checking (Basedpyright)
3. Unit tests
4. Integration tests
5. Coverage report

See `.github/workflows/test.yml` for configuration.

## Best Practices

### 1. Test One Thing

```python
# Good
def test_addition():
    assert add(2, 2) == 4

# Bad - testing multiple things
def test_everything():
    assert add(2, 2) == 4
    assert subtract(5, 3) == 2
    assert multiply(3, 4) == 12
```

### 2. Use Descriptive Names

```python
# Good
def test_user_login_with_invalid_password_returns_error():
    pass

# Bad
def test_login():
    pass
```

### 3. Arrange-Act-Assert

```python
def test_example():
    # Arrange
    user = User("test")

    # Act
    result = user.login("password")

    # Assert
    assert result is True
```

### 4. Test Edge Cases

```python
@pytest.mark.parametrize("value", [
    0,           # Zero
    -1,          # Negative
    999999,      # Large
    None,        # Null
    "",          # Empty
])
def test_edge_cases(value):
    """Test edge cases."""
    result = handle_value(value)
    assert result is not None
```

## Troubleshooting

??? question "Tests hang?"

    - Add timeout: `@pytest.mark.timeout(5)`
    - Check for deadlocks in async code
    - Use `pytest -v` for verbose output

??? question "Flaky tests?"

    - Add retries: `@pytest.mark.flaky(reruns=3)`
    - Fix timing issues
    - Mock external dependencies

??? question "Coverage too low?"

    - Add tests for untested code
    - Remove dead code
    - Test error paths

## Next Steps

- [Development Guide](development.md) - Development workflow
