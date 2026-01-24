# Installation

Detailed installation guide for Relace MCP.

## System Requirements

- **Python**: 3.11 or higher
- **uv**: Latest version ([install guide](https://docs.astral.sh/uv/))
- **git**: Any recent version
- **ripgrep** (optional): For faster code search

## Installation Methods

### Method 1: uv tool (Recommended)

The easiest way to install Relace MCP:

```bash
uv tool install relace-mcp
```

This installs `relace-mcp` in an isolated environment and makes it available globally.

**Verify installation:**

```bash
uv tool list
# Should show: relace-mcp v0.2.5
```

### Method 2: pip

Using pip (system-wide or in a virtual environment):

```bash
# System-wide (may require sudo)
pip install relace-mcp

# In a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install relace-mcp
```

### Method 3: Development Installation

For development or contributing:

```bash
# Clone repository
git clone https://github.com/possible055/relace-mcp.git
cd relace-mcp

# Install with all development dependencies
uv sync --all-extras --group dev

# Install in editable mode
uv pip install -e .
```

## Optional Dependencies

### ripgrep

Significantly improves search performance:

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
    # or
    scoop install ripgrep
    ```

### Development Tools

For contributing to Relace MCP:

```bash
# Install all extras
uv sync --all-extras --group dev

# Just development tools
uv sync --extra dev --group dev

# Specific extras
uv sync --extra tools      # Dashboard tools
uv sync --extra benchmark  # Benchmark tools
```

## Upgrading

### uv tool

```bash
uv tool upgrade relace-mcp
```

### pip

```bash
pip install --upgrade relace-mcp
```

## Uninstalling

### uv tool

```bash
uv tool uninstall relace-mcp
```

### pip

```bash
pip uninstall relace-mcp
```

## Troubleshooting

??? question "uv not found?"

    Install uv first:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

??? question "Python version mismatch?"

    Check your Python version:
    ```bash
    python --version
    ```

    Must be 3.11 or higher. Install from [python.org](https://www.python.org/downloads/).

??? question "Permission errors?"

    Use `uv tool install` instead of system-wide `pip install`, or use a virtual environment.

## Next Steps

- [Quick Start](quick-start.md) - Get started in 5 minutes
- [Configuration](configuration.md) - Configure your MCP client
