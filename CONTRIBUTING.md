# Contributing to Relace MCP

Thank you for your interest in contributing to Relace MCP! We welcome contributions from the community to help improve this project.

## Development Environment

This project uses [uv](https://github.com/astral-sh/uv) for dependency management and packaging.

1.  **Install uv**:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Clone the repository**:
    ```bash
    git clone https://github.com/possible055/relace-mcp.git
    cd relace-mcp
    ```

3.  **Install dependencies**:
    ```bash
    uv sync --extra dev
    ```

## Coding Standards

We enforce strict coding standards to ensure code quality and consistency.

### linting & Formatting

We use [Ruff](https://github.com/astral-sh/ruff) for both linting and formatting.

*   **Check code**:
    ```bash
    uv run ruff check .
    ```
*   **Format code**:
    ```bash
    uv run ruff format .
    ```

All pull requests must pass the linter and formatter checks.

### Type Hints

We use static type checking. While not fully strict yet, we aim for high type coverage.

*   Ensure all new functions and classes have type hints.
*   You can verify types using `mypy` (installed in dev environment):
    ```bash
    uv run mypy src tests
    ```

## Testing

We use `pytest` for testing.

*   **Run all tests**:
    ```bash
    uv run pytest
    ```
*   **Run with coverage**:
    ```bash
    uv run pytest --cov=relace_mcp
    ```

**Requirements:**
1.  All new features must include unit tests.
2.  Bug fixes must include a regression test.
3.  All existing tests must pass.

## Submission Guidelines

1.  Fork the repository and create your branch from `main`.
2.  Make sure your code lints, formats, and passes tests.
3.  Create a Pull Request with a clear title and description.
4.  Link any relevant issues in the PR description.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
