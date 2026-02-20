# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.5] - TBD

### Added

- **Pluggable code indexing backends** — `MCP_RETRIEVAL_BACKEND` supports `relace`, `codanna`, `chunkhound`, or `none`.
- **Local semantic hints** — Codanna (local index) and ChunkHound (auto-index) support for `agentic_retrieval` without cloud dependency.
- **Cross-platform workspace storage** — IDE-aware workspace detection for VSCode, Cursor, Windsurf, and Zed across platforms.

### Changed

- **`MCP_LOGGING` unified** — Now accepts `off` (default), `safe` (with redaction), or `full` (no redaction). Replaces separate `MCP_LOGGING` and `MCP_LOG_REDACT` variables.
- **`MCP_SEARCH_MODE` → `MCP_SEARCH_RETRIEVAL`** — Simplified boolean flag (`1` to enable `agentic_retrieval` tool).
- **`agentic_retrieval` parameter simplification** — Removed `branch`, `score_threshold`, and `max_hints` parameters; only `query` is required.
- **Tool descriptions enhanced** — Improved consistency and clarity across all MCP tools.

### Removed

- **`fast_search` tool** — Use `agentic_search` instead.
- **`MCP_SEARCH_MODE` environment variable** — Use `MCP_SEARCH_RETRIEVAL=1` instead.
- **`MCP_LOG_REDACT` environment variable** — Integrated into `MCP_LOGGING` values (`safe` or `full`).
- **`agentic_retrieval` parameters** — `branch`, `score_threshold`, and `max_hints` removed.
- **Provider-specific API key auto-derivation** — `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `CEREBRAS_API_KEY` are no longer auto-detected. Use `APPLY_API_KEY` / `SEARCH_API_KEY` explicitly for non-Relace providers.
- **Deprecated environment variables** — All `RELACE_*` prefixed aliases removed:
  - `RELACE_APPLY_ENDPOINT` → Use `APPLY_ENDPOINT`
  - `RELACE_APPLY_MODEL` → Use `APPLY_MODEL`
  - `RELACE_APPLY_PROVIDER` → Use `APPLY_PROVIDER`
  - `RELACE_APPLY_API_KEY` → Use `APPLY_API_KEY`
  - `RELACE_TIMEOUT_SECONDS` → Use `APPLY_TIMEOUT_SECONDS`
  - `RELACE_SEARCH_ENDPOINT` → Use `SEARCH_ENDPOINT`
  - `RELACE_SEARCH_MODEL` → Use `SEARCH_MODEL`
  - `RELACE_SEARCH_PROVIDER` → Use `SEARCH_PROVIDER`
  - `RELACE_SEARCH_API_KEY` → Use `SEARCH_API_KEY`
  - `RELACE_SEARCH_TIMEOUT_SECONDS` → Use `SEARCH_TIMEOUT_SECONDS`
  - `RELACE_SEARCH_MAX_TURNS` → Use `SEARCH_MAX_TURNS`
  - `RELACE_SEARCH_PARALLEL_TOOL_CALLS` → Use `SEARCH_PARALLEL_TOOL_CALLS`
  - `RELACE_SEARCH_ENABLED_TOOLS` → Use `SEARCH_ENABLED_TOOLS`
  - `RELACE_SEARCH_TOOL_STRICT` → Use `SEARCH_TOOL_STRICT`
  - `RELACE_SEARCH_PROMPT_FILE` → Use `SEARCH_PROMPT_FILE`
  - `RELACE_APPLY_PROMPT_FILE` → Use `APPLY_PROMPT_FILE`
  - `RELACE_LSP_TIMEOUT_SECONDS` → Use `SEARCH_LSP_TIMEOUT_SECONDS`
  - `RELACE_LSP_MAX_CLIENTS` → Use `SEARCH_LSP_MAX_CLIENTS`
  - `RELACE_BASE_DIR` → Use `MCP_BASE_DIR`
  - `RELACE_LOGGING` → Use `MCP_LOGGING`
  - `RELACE_DOTENV_PATH` → Use `MCP_DOTENV_PATH`
  - `APPLY_POST_CHECK` → Use `APPLY_SEMANTIC_CHECK`

## [0.2.4] - 2025-01-22

### Added

#### Tools

- **`agentic_search`** — New primary tool for agentic codebase search. Replaces `fast_search`.
- **`agentic_retrieval`** — Two-stage semantic + agentic code retrieval (requires `MCP_SEARCH_RETRIEVAL=1`).

#### LSP Integration

- **Multi-language LSP support** — Extended toolset with `find_symbol`, `search_symbol`, `get_type`, `list_symbols`, `call_graph` for Python, TypeScript, Go, and Rust.
- **Session-based LSP lifecycle** — Improved state isolation and fingerprint-based caching.

#### Configuration

- **`MCP_SEARCH_RETRIEVAL`** — Set to `1` to enable `agentic_retrieval` tool.
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
