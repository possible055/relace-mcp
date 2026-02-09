# 环境变量

Relace MCP 通过环境变量进行配置的完整参考。

!!! note "在哪里设置"
    你可以在 shell 中设置，或在 MCP 客户端配置的 `env` 区块中设置。

## 核心

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RELACE_API_KEY` | — | 从 [Dashboard](https://app.relace.ai/settings/billing) 获取的 Relace API key。使用 Relace provider 或云端工具时必需。 |
| `MCP_BASE_DIR` | — | 限制文件操作范围。未设置时，server 会在运行时从 MCP Roots 解析 base dir。 |
| `MCP_DOTENV_PATH` | — | 启动时加载的 `.env` 文件路径。未设置时会使用 dotenv 的默认搜索逻辑。 |
| `RELACE_DEFAULT_ENCODING` | — | 强制项目文件默认编码（如 `gbk`、`big5`）。未设置时会自动检测。 |

> **注意：** 仅当**同时满足**以下条件时可省略 `RELACE_API_KEY`：(1) `APPLY_PROVIDER` 和 `SEARCH_PROVIDER` 使用非 Relace provider，且 (2) `RELACE_CLOUD_TOOLS=0`。

## 功能开关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RELACE_CLOUD_TOOLS` | `0` | 启用云端工具（`cloud_sync`、`cloud_search`、`cloud_info`、`cloud_list`、`cloud_clear`）。 |
| `MCP_SEARCH_RETRIEVAL` | `0` | 启用 `agentic_retrieval` 工具。 |
| `MCP_RETRIEVAL_BACKEND` | `relace` | `agentic_retrieval` 的检索后端：`relace`、`codanna`、`chunkhound`，或 `none`（禁用语义提示）。 |

## 日志

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_LOG_LEVEL` | `WARNING` | stderr 的 Python 日志级别（如 `DEBUG`、`INFO`、`WARNING`、`ERROR`）。 |
| `MCP_LOGGING` | `off` | 本地 JSONL 文件日志：`off`、`safe`（脱敏）、`full`（不脱敏）。 |

## Fast Apply

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APPLY_PROVIDER` | `relace` | provider 标识（`relace`、`openai`、`openrouter`、`cerebras` 等）。 |
| `APPLY_ENDPOINT` | (Relace 官方) | 覆盖 base URL（OpenAI-compatible）。 |
| `APPLY_MODEL` | `auto` | 覆盖模型名称。 |
| `APPLY_API_KEY` | — | 非 Relace provider 的 API key（优先于派生 key）。 |
| `APPLY_PROMPT_FILE` | — | 覆盖 apply prompt YAML 路径。 |
| `APPLY_TIMEOUT_SECONDS` | `60` | 请求超时（秒）。 |
| `APPLY_TEMPERATURE` | `0.0` | 采样温度（0.0–2.0）。 |
| `APPLY_SEMANTIC_CHECK` | `0` | 合并后语义验证（可能增加失败率）。 |

## Agentic Search

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SEARCH_PROVIDER` | `relace` | provider 标识（`relace`、`openai`、`openrouter`、`cerebras` 等）。 |
| `SEARCH_ENDPOINT` | (Relace 官方) | 覆盖 base URL（OpenAI-compatible）。 |
| `SEARCH_MODEL` | `relace-search` | 覆盖模型名称。 |
| `SEARCH_API_KEY` | — | 非 Relace provider 的 API key（优先于派生 key）。 |
| `SEARCH_PROMPT_FILE` | — | 覆盖 search prompt YAML 路径。 |
| `SEARCH_TIMEOUT_SECONDS` | `120` | 请求超时（同时作为 `agentic_search` 的总耗时预算）。 |
| `SEARCH_TEMPERATURE` | `1.0` | 采样温度（0.0–2.0）。 |
| `SEARCH_TOP_P` | — | 可选 top_p（仅在 provider 需要时设置）。 |
| `SEARCH_MAX_TURNS` | `6` | 最大 agent 循环轮数。 |
| `SEARCH_PARALLEL_TOOL_CALLS` | `1` | 启用并行工具调用。 |
| `SEARCH_TOOL_STRICT` | `1` | 在 tool schema 中包含非标准 `strict` 字段（provider 不接受时可设为 `0`）。 |
| `SEARCH_ENABLED_TOOLS` | (仅基础工具) | 工具 allowlist（逗号/空格分隔）。`bash` 需要显式加入。 |
| `SEARCH_LSP_TOOLS` | `false` | LSP 工具模式：`false`、`true`、`auto`。 |
| `SEARCH_LSP_TIMEOUT_SECONDS` | `15.0` | LSP 启动/请求超时。 |
| `SEARCH_LSP_MAX_CLIENTS` | `2` | 最大并发 LSP 客户端数。 |

## 云端工具

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` | 云端操作 API 端点。 |
| `RELACE_REPO_ID` | — | 预配置的 repo UUID（跳过 list/create）。 |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` | 同步操作超时。 |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` | 每次同步最大文件数。 |
| `RELACE_REPO_LIST_MAX` | `10000` | 最大获取仓库数。 |
| `RELACE_UPLOAD_MAX_WORKERS` | `8` | 并发上传工作线程数。 |
| `RELACE_AGENTIC_AUTO_SYNC` | `1` | 启用云端工具时，在 `agentic_retrieval` 前自动同步。 |

## Provider API Keys

使用非 Relace provider 时，可设置 provider-specific API key：

| 变量 | 使用场景 |
|------|----------|
| `OPENAI_API_KEY` | `*_PROVIDER=openai` 且未设置 `*_API_KEY` |
| `OPENROUTER_API_KEY` | `*_PROVIDER=openrouter` 且未设置 `*_API_KEY` |
| `CEREBRAS_API_KEY` | `*_PROVIDER=cerebras` 且未设置 `*_API_KEY` |

## 参见

- [高级用法](overview.md) - 高级主题
- [工具参考](../tools/reference.md) - tool schema 与回传格式
