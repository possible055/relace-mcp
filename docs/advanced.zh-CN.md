# 进阶用法

本文档涵盖面向进阶用户和开发者的高级配置选项。

## 目录

- [同步模式](#同步模式)
- [开发者覆盖](#开发者覆盖)
- [编码](#编码)
- [日志](#日志)
- [Fast Apply 提供商切换](#fast-apply-提供商切换)
- [Fast Search 提供商切换](#fast-search-提供商切换)
- [Fast Search 工具控制](#fast-search-工具控制)
  - [LSP 工具](#lsp-工具)
- [远程部署 (Streamable HTTP)](#远程部署-streamable-http)

---

## 同步模式

`cloud_sync` 工具支持三种同步模式：

| 模式 | 触发条件 | 描述 |
|------|----------|------|
| 增量同步 | (默认) | 仅上传新增/修改的文件，删除已移除的文件 |
| 安全完整同步 | `force=True`、首次同步或 HEAD 变更 | 上传所有文件；除非 HEAD 变更，否则抑制删除 |
| 镜像完整同步 | `force=True, mirror=True` | 完全覆盖云端以匹配本地 |

### HEAD 变更检测

当 git HEAD 自上次同步后发生变化（如分支切换、rebase、commit amend），安全完整同步模式会自动清理旧 ref 的僵尸文件，防止搜索结果过时。

---

## 开发者覆盖

这些设置允许在官方 API 更新但包尚未跟进时进行临时覆盖：

| 变量 | 默认值 |
|------|--------|
| `RELACE_APPLY_ENDPOINT` | `https://instantapply.endpoint.relace.run/v1/apply` |
| `RELACE_APPLY_MODEL` | `auto` |
| `RELACE_TIMEOUT_SECONDS` | `60` |
| `RELACE_MAX_RETRIES` | `3` |
| `RELACE_RETRY_BASE_DELAY` | `1.0` |
| `RELACE_SEARCH_ENDPOINT` | `https://search.endpoint.relace.run/v1/search` |
| `RELACE_SEARCH_MODEL` | `relace-search` |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `120` |
| `RELACE_SEARCH_MAX_TURNS` | `6` |
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` |
| `RELACE_REPO_ID` | — (预配置的 repo UUID，可跳过 list/create) |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` |
| `RELACE_REPO_LIST_MAX` | `10000`（分页获取的最大仓库数） |
| `RELACE_UPLOAD_MAX_WORKERS` | `8`（并发文件哈希/上传工作线程数） |

---

## 编码

Relace MCP 旨在支持遗留编码仓库（如 GBK/Big5），不会导致 `fast_apply`、`view_file`、`grep_search` 和 `cloud_sync` 等工具崩溃。

**推荐最佳实践：** 将仓库转换为 UTF-8（并保持一致）。如果必须保留遗留编码：

- 对于 Python 源文件，在第一或第二行添加 PEP 263 编码声明（如 `# -*- coding: gbk -*-`）。
- 如果仓库主要使用单一遗留编码，请显式设置 `RELACE_DEFAULT_ENCODING`。

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_DEFAULT_ENCODING` | — | 强制读写项目文件时使用的默认编码（如 `gbk`、`big5`） |
| `RELACE_ENCODING_SAMPLE_LIMIT` | `30` | 启动时用于自动检测主要项目编码的采样文件上限 |

---

## 日志

文件日志为可选功能。使用 `RELACE_LOGGING=1` 启用。

### 日志位置

日志写入跨平台状态目录：

| 平台 | 路径 |
|------|------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

### 日志格式

日志以 JSON Lines (JSONL) 格式写入，每行一个 JSON 对象：

```json
{"kind":"apply_success","level":"info","trace_id":"a1b2c3d4","started_at":"2025-01-01T00:00:00+00:00","latency_ms":150,"file_path":"/path/to/file.py","file_size_bytes":1234,"instruction":"fix bug","edit_snippet_preview":"def foo():...","usage":{"prompt_tokens":100,"completion_tokens":50},"timestamp":"2025-01-01T00:00:00.150000+00:00"}
```

### 事件类型

| 事件类型 | 描述 |
|----------|------|
| `create_success` | 新文件创建成功 |
| `apply_success` | 编辑应用成功 |
| `apply_error` | 编辑应用失败 |
| `search_start` | 搜索开始 |
| `search_turn` | Agent 循环回合状态 |
| `tool_call` | 工具调用（含计时） |
| `search_complete` | 搜索完成 |
| `search_error` | 搜索失败 |

### 日志轮转

- 超过 **10 MB** 时自动轮转
- 最多保留 **5** 个轮转日志文件
- 旧文件命名格式：`relace.YYYYMMDD_HHMMSS.log`

### 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_LOGGING` | `0` | 设为 `1` 启用文件日志 |
| `RELACE_EXPERIMENTAL_LOGGING` | — | `RELACE_LOGGING` 的弃用别名（向后兼容） |

---

## Fast Apply 提供商切换

切换到 OpenAI 兼容提供商用于 `fast_apply`：

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_APPLY_PROVIDER` | `relace` | 提供商标签。`relace` 使用 `RELACE_API_KEY`；其他值使用对应提供商的 API key。 |
| `RELACE_APPLY_ENDPOINT` | — | 可选覆盖 base URL（SDK 会 POST 到 `/chat/completions`；尾部的 `/chat/completions` 会自动剥离）。 |
| `RELACE_APPLY_MODEL` | — | 可选覆盖模型 |
| `RELACE_APPLY_API_KEY` | — | 可选直接 API key 覆盖（非 Relace 提供商推荐使用） |
| `RELACE_APPLY_API_KEY_ENV` | — | 可选：持有 API key 的环境变量名 |
| `RELACE_APPLY_HEADERS` | — | 可选 JSON 对象用于默认 headers（如 `{\"HTTP-Referer\":\"...\",\"X-Title\":\"...\"}`) |
| `OPENAI_API_KEY` | — | 当 `RELACE_APPLY_PROVIDER=openai` 且未设置 `RELACE_APPLY_API_KEY*` 时使用 |
| `OPENROUTER_API_KEY` | — | 当 `RELACE_APPLY_PROVIDER=openrouter` 且未设置 `RELACE_APPLY_API_KEY*` 时使用 |
| `CEREBRAS_API_KEY` | — | 当 `RELACE_APPLY_PROVIDER=cerebras` 且未设置 `RELACE_APPLY_API_KEY*` 时使用 |

---

## Fast Search 提供商切换

切换到 OpenAI 兼容提供商用于 `fast_search`：

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_SEARCH_PROVIDER` | `relace` | 提供商标签。`relace` 使用 `RELACE_API_KEY`；其他值使用对应提供商的 API key。 |
| `RELACE_SEARCH_ENDPOINT` | — | 可选覆盖 base URL（SDK 会 POST 到 `/chat/completions`；尾部的 `/chat/completions` 会自动剥离）。 |
| `RELACE_SEARCH_MODEL` | — | 可选覆盖模型 |
| `RELACE_SEARCH_API_KEY` | — | 可选直接 API key 覆盖（非 Relace 提供商推荐使用） |
| `RELACE_SEARCH_API_KEY_ENV` | — | 可选：持有 API key 的环境变量名 |
| `RELACE_SEARCH_HEADERS` | — | 可选 JSON 对象用于默认 headers（如 `{\"HTTP-Referer\":\"...\",\"X-Title\":\"...\"}`) |
| `RELACE_SEARCH_TOOL_STRICT` | `1` | 设为 `0` 可从 tool schemas 中省略非标准的 `strict` 字段 |
| `OPENAI_API_KEY` | — | 当 `RELACE_SEARCH_PROVIDER=openai` 且未设置 `RELACE_SEARCH_API_KEY*` 时使用 |
| `OPENROUTER_API_KEY` | — | 当 `RELACE_SEARCH_PROVIDER=openrouter` 且未设置 `RELACE_SEARCH_API_KEY*` 时使用 |
| `CEREBRAS_API_KEY` | — | 当 `RELACE_SEARCH_PROVIDER=cerebras` 且未设置 `RELACE_SEARCH_API_KEY*` 时使用 |

---

## Fast Search 工具控制

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_SEARCH_ENABLED_TOOLS` | `view_file,view_directory,grep_search,glob,find_symbol` | 逗号分隔的允许列表。`report_back` 始终启用。添加 `bash` 可启用 shell 命令（仅 Unix）。 |
| `RELACE_SEARCH_PARALLEL_TOOL_CALLS` | `1` | 启用并行工具调用以降低延迟 |

> **注意：** `bash` 工具默认禁用以确保安全。在 Unix 系统上启用，请在 MCP 配置中添加：
> ```json
> {
>   "mcpServers": {
>     "relace": {
>       "env": {
>         "RELACE_SEARCH_ENABLED_TOOLS": "view_file,view_directory,grep_search,glob,find_symbol,bash"
>       }
>     }
>   }
> }
> ```

### LSP 工具

`find_symbol` 工具通过 Language Server Protocol 提供 Python 文件的语义代码查询。支持：
- `definition`：跳转到符号定义
- `references`：查找符号的所有引用

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_LSP_TIMEOUT_SECONDS` | `15.0` | LSP 启动/关闭/请求的超时时间 |
| `RELACE_LSP_LOOP_STOP_TIMEOUT_SECONDS` | `3.0` | 停止 LSP 循环线程的看门狗超时 |

> **注意：** LSP 需要 `multilspy`（随包安装）和 `jedi-language-server`。首次调用会有 2-5 秒启动延迟。

### OpenAI Structured Outputs 兼容性

使用 OpenAI 或 OpenAI 兼容提供商（非 `relace`）且 `RELACE_SEARCH_TOOL_STRICT=1`（默认）时，`parallel_tool_calls` 会自动禁用以符合 [OpenAI 的 Structured Outputs 限制](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs)。

要在 OpenAI 提供商上使用并行工具调用，请禁用 strict 模式：

```bash
export RELACE_SEARCH_TOOL_STRICT=0
export RELACE_SEARCH_PARALLEL_TOOL_CALLS=1
```

---

## 远程部署 (Streamable HTTP)

用于远程部署，以 streamable-http transport 运行：

```bash
relace-mcp -t streamable-http -p 8000
```

连接配置：

```json
{
  "mcpServers": {
    "relace": {
      "type": "streamable-http",
      "url": "http://your-server:8000/mcp"
    }
  }
}
```

### 其他 CLI 选项

| 选项 | 默认值 | 描述 |
|------|--------|------|
| `--host` | `0.0.0.0` | 绑定地址 |
| `--port`, `-p` | `8000` | 端口号 |
| `--path` | `/mcp` | MCP 端点的 URL 路径 |
