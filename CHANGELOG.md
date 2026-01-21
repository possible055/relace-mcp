# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.5] - TBD

### Removed

- **`fast_search` tool** — Use `agentic_search` instead.
- **Deprecated environment variables** — All `RELACE_*` prefixed aliases removed:
  - `RELACE_APPLY_ENDPOINT` → Use `APPLY_ENDPOINT`
  - `RELACE_APPLY_MODEL` → Use `APPLY_MODEL`
  - `RELACE_TIMEOUT_SECONDS` → Use `APPLY_TIMEOUT_SECONDS`
  - `RELACE_SEARCH_ENDPOINT` → Use `SEARCH_ENDPOINT`
  - `RELACE_SEARCH_MODEL` → Use `SEARCH_MODEL`
  - `RELACE_SEARCH_TIMEOUT_SECONDS` → Use `SEARCH_TIMEOUT_SECONDS`
  - `RELACE_SEARCH_MAX_TURNS` → Use `SEARCH_MAX_TURNS`
  - `RELACE_SEARCH_PARALLEL_TOOL_CALLS` → Use `SEARCH_PARALLEL_TOOL_CALLS`
  - `RELACE_SEARCH_PROVIDER` → Use `SEARCH_PROVIDER`
  - `RELACE_SEARCH_API_KEY` → Use `SEARCH_API_KEY`
  - `RELACE_APPLY_PROVIDER` → Use `APPLY_PROVIDER`
  - `RELACE_APPLY_API_KEY` → Use `APPLY_API_KEY`
  - `RELACE_BASE_DIR` → Use `MCP_BASE_DIR`
  - `RELACE_LOGGING` → Use `MCP_LOGGING`
  - `APPLY_POST_CHECK` → Use `APPLY_SEMANTIC_CHECK`

## [0.2.4] - 2025-01-22

### Added

#### Tools

- **`agentic_search`** — New primary tool for agentic codebase search. Replaces `fast_search`.
- **`agentic_retrieval`** — Two-stage semantic + agentic code retrieval (requires `RELACE_CLOUD_TOOLS=true` and `MCP_SEARCH_MODE=indexed|both`).

#### LSP Integration

- **Multi-language LSP support** — Extended toolset with `find_symbol`, `find_references`, `get_hover` for Python, TypeScript, Go, and Rust.
- **Session-based LSP lifecycle** — Improved state isolation and fingerprint-based caching.

#### Configuration

- **`MCP_SEARCH_MODE`** — Control search mode: `agentic` (default), `indexed`, or `both`.
- **`SEARCH_LSP_TOOLS`** — Gatekeeper for LSP tool enablement (`true`, `false`, `auto`).
- **`SEARCH_TOP_P`** — Optional sampling control for providers requiring explicit top_p (e.g., Mistral).
- **Third-party provider support** — Relaxed API key requirements; auto-derive keys from `{PROVIDER}_API_KEY`.

#### Benchmark

- **Benchmark CLI tools** — `curate`, `report`, checkpoint resume, timeout, and fail-fast support for Loc-Bench evaluation.

### Changed

- **`RELACE_BASE_DIR` → `MCP_BASE_DIR`** — Environment variable renamed for consistency.
- **`RELACE_LOGGING` → `MCP_LOGGING`** — Environment variable renamed.
- **Dual-channel parallel search** — Internal refactor for fine-grained benchmark metrics.
- **Tool descriptions streamlined** — Improved consistency across all MCP tools.

### Fixed

- Cloud hash parameter and gitignore unignore semantics.
- Branch handling and hash usage in cloud search logic.
- Mistral API compatibility for assistant messages.
- Security hardening for LSP path validation and symlink traversal.

### Deprecated

The following will be **removed in v0.2.5**. Migration warnings are emitted when deprecated items are used.

#### Tools

| Deprecated | Replacement | Notes |
|------------|-------------|-------|
| `fast_search` | `agentic_search` | Returns `_deprecated` field in response |

#### Environment Variables

| Deprecated | Replacement |
|------------|-------------|
| `RELACE_APPLY_ENDPOINT` | `APPLY_ENDPOINT` |
| `RELACE_APPLY_MODEL` | `APPLY_MODEL` |
| `RELACE_TIMEOUT_SECONDS` | `APPLY_TIMEOUT_SECONDS` |
| `RELACE_SEARCH_ENDPOINT` | `SEARCH_ENDPOINT` |
| `RELACE_SEARCH_MODEL` | `SEARCH_MODEL` |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `SEARCH_TIMEOUT_SECONDS` |
| `RELACE_SEARCH_MAX_TURNS` | `SEARCH_MAX_TURNS` |
| `RELACE_SEARCH_PARALLEL_TOOL_CALLS` | `SEARCH_PARALLEL_TOOL_CALLS` |
| `RELACE_SEARCH_PROVIDER` | `SEARCH_PROVIDER` |
| `RELACE_SEARCH_API_KEY` | `SEARCH_API_KEY` |
| `RELACE_APPLY_PROVIDER` | `APPLY_PROVIDER` |
| `RELACE_APPLY_API_KEY` | `APPLY_API_KEY` |
| `RELACE_BASE_DIR` | `MCP_BASE_DIR` |
| `RELACE_LOGGING` | `MCP_LOGGING` |
| `APPLY_POST_CHECK` | `APPLY_SEMANTIC_CHECK` |

### Migration Guide

1. **Update tool calls**: Replace `fast_search` with `agentic_search` in your MCP client configuration.
2. **Update environment variables**: Rename deprecated `RELACE_*` variables to their new names.
3. **Check logs**: `DeprecationWarning` messages indicate which deprecated items are still in use.

[Unreleased]: https://github.com/anthropics/relace-mcp/compare/v0.2.5...HEAD
[0.2.5]: https://github.com/anthropics/relace-mcp/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/anthropics/relace-mcp/releases/tag/v0.2.4
