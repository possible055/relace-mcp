# Relace MCP

!!! warning "Unofficial Project"
    This is a **personal project** and is not affiliated with Relace.

!!! info "Built with AI"
    Developed entirely with AI assistance (Antigravity, Codex, Cursor, Github Copilot, Windsurf).

MCP server providing AI-powered code editing and intelligent codebase exploration tools.

## Key Features

=== "Fast Apply"

    Apply code edits at **10,000+ tokens/sec** via Relace API

    - Line-accurate merging
    - Preserves formatting
    - Handles conflicts automatically

=== "Agentic Search"

    Natural language codebase exploration

    - Ask questions in plain language
    - Get precise code locations
    - Trace imports and dependencies

=== "Cloud Search"

    Semantic search over cloud repositories

    - Sync multiple repositories
    - Cross-repo search
    - Fast semantic indexing

## Comparison

| Without MCP | With `fast_apply` + `agentic_search` |
|:------------|:-------------------------------------|
| Manual grep, misses related files | Ask naturally, get precise locations |
| Edits break imports elsewhere | Traces imports and call chains |
| Full rewrites burn tokens | Describe changes, no line numbers |
| Line number errors corrupt code | 10,000+ tokens/sec merging |

## Quick Start

Get started in 5 minutes:

1. **Install**: `uv tool install relace-mcp`
2. **Configure**: Add to your MCP client (Cursor, Claude Desktop, etc.)
3. **Use**: Start using AI-powered code tools

[Get Started](getting-started/quick-start.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/possible055/relace-mcp){ .md-button }

## Documentation Structure

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __Getting Started__

    ---

    Installation, configuration, and basic usage

    [:octicons-arrow-right-24: Quick Start](getting-started/quick-start.md)

-   :material-tools:{ .lg .middle } __Tools__

    ---

    Detailed documentation for each MCP tool

    [:octicons-arrow-right-24: Tools Overview](tools/index.md)

-   :material-rocket-launch:{ .lg .middle } __Advanced__

    ---

    Dashboard, benchmarks, and API reference

    [:octicons-arrow-right-24: Advanced Topics](advanced/index.md)

-   :material-account-group:{ .lg .middle } __Contributing__

    ---

    Development guide and contribution guidelines

    [:octicons-arrow-right-24: Contribute](contributing/index.md)

</div>

## Prerequisites

- [uv](https://docs.astral.sh/uv/) - Python package installer
- [git](https://git-scm.com/) - Version control
- [ripgrep](https://github.com/BurntSushi/ripgrep) (recommended) - Fast search

## Community

- **Issues**: [GitHub Issues](https://github.com/possible055/relace-mcp/issues)
- **PyPI**: [relace-mcp](https://pypi.org/project/relace-mcp/)

## License

This project is licensed under the [MIT License](https://github.com/possible055/relace-mcp/blob/main/LICENSE).
