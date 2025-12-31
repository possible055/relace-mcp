# 进阶用法

本文档涵盖面向进阶用户和开发者的高级配置选项。

## 目录

- [环境变量参考](#环境变量参考)
- [同步模式](#同步模式)
- [日志](#日志)
- [替代提供商](#替代提供商)
- [远程部署 (Streamable HTTP)](#远程部署-streamable-http)

---

## 环境变量参考

所有环境变量可在 shell 中设置，或在 MCP 配置的 `env` 部分中设置。

### 核心

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_API_KEY` | — | **必需。** 你的 Relace API key |
| `RELACE_BASE_DIR` | 当前目录 | 限制文件访问范围 |
| `RELACE_DEFAULT_ENCODING` | — | 强制项目文件编码（如 `gbk`、`big5`） |
| `RELACE_LOGGING` | `0` | 设为 `1` 启用文件日志 |

### Fast Apply

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_APPLY_PROVIDER` | `relace` | 提供商：`relace`、`openai`、`openrouter`、`cerebras` 等 |
| `RELACE_APPLY_ENDPOINT` | (Relace 官方) | 覆盖 base URL |
| `RELACE_APPLY_MODEL` | `auto` | 覆盖模型名称 |
| `RELACE_APPLY_API_KEY` | — | 非 Relace 提供商的 API key |
| `RELACE_APPLY_PROMPT_FILE` | — | 覆盖 apply prompt YAML 路径 |
| `RELACE_TIMEOUT_SECONDS` | `60` | 请求超时 |

### Fast Search

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_SEARCH_PROVIDER` | `relace` | 提供商：`relace`、`openai`、`openrouter`、`cerebras` 等 |
| `RELACE_SEARCH_ENDPOINT` | (Relace 官方) | 覆盖 base URL |
| `RELACE_SEARCH_MODEL` | `relace-search` | 覆盖模型名称 |
| `RELACE_SEARCH_API_KEY` | — | 非 Relace 提供商的 API key |
| `RELACE_SEARCH_PROMPT_FILE` | — | 覆盖 search prompt YAML 路径 |
| `RELACE_SEARCH_TIMEOUT_SECONDS` | `120` | 请求超时 |
| `RELACE_SEARCH_MAX_TURNS` | `6` | 最大 agent 循环轮数 |
| `RELACE_SEARCH_ENABLED_TOOLS` | `view_file,view_directory,grep_search,glob,find_symbol` | 工具允许列表（逗号分隔） |
| `RELACE_SEARCH_PARALLEL_TOOL_CALLS` | `1` | 启用并行工具调用 |
| `RELACE_SEARCH_TOOL_STRICT` | `1` | 在 tool schema 中包含 `strict` 字段 |
| `RELACE_LSP_TIMEOUT_SECONDS` | `15.0` | LSP 启动/请求超时 |

### Cloud Sync

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_API_ENDPOINT` | `https://api.relace.run/v1` | 云操作 API 端点 |
| `RELACE_REPO_ID` | — | 预配置的 repo UUID（跳过 list/create） |
| `RELACE_REPO_SYNC_TIMEOUT` | `300` | 同步操作超时 |
| `RELACE_REPO_SYNC_MAX_FILES` | `5000` | 每次同步最大文件数 |
| `RELACE_REPO_LIST_MAX` | `10000` | 最大获取仓库数 |
| `RELACE_UPLOAD_MAX_WORKERS` | `8` | 并发上传工作线程数 |

### 第三方 API Keys

使用替代提供商时，设置对应的 API key：

| 变量 | 使用场景 |
|------|----------|
| `OPENAI_API_KEY` | `*_PROVIDER=openai` 且未设置 `*_API_KEY` |
| `OPENROUTER_API_KEY` | `*_PROVIDER=openrouter` 且未设置 `*_API_KEY` |
| `CEREBRAS_API_KEY` | `*_PROVIDER=cerebras` 且未设置 `*_API_KEY` |

### 实验性

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `RELACE_EXPERIMENTAL_POST_CHECK` | `0` | `fast_apply` 后额外验证（可能增加失败率） |
| `RELACE_EXPERIMENTAL_LOGGING` | — | `RELACE_LOGGING` 的弃用别名 |

---

## 同步模式

`cloud_sync` 工具支持三种同步模式：

| 模式 | 触发条件 | 描述 |
|------|----------|------|
| 增量同步 | (默认) | 仅上传新增/修改的文件，删除已移除的文件 |
| 安全完整同步 | `force=True`、首次同步或 HEAD 变更 | 上传所有文件；除非 HEAD 变更，否则抑制删除 |
| 镜像完整同步 | `force=True, mirror=True` | 完全覆盖云端以匹配本地 |

当 git HEAD 自上次同步后发生变化（如分支切换、rebase），安全完整同步模式会自动清理旧 ref 的僵尸文件。

---

## 日志

文件日志为可选功能。使用 `RELACE_LOGGING=1` 启用。

### 日志位置

| 平台 | 路径 |
|------|------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

### 日志格式

日志以 JSON Lines (JSONL) 格式写入：

```json
{"kind":"apply_success","level":"info","trace_id":"a1b2c3d4","latency_ms":150,"file_path":"/path/to/file.py",...}
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
- 最多保留 **5** 个轮转文件
- 命名格式：`relace.YYYYMMDD_HHMMSS.log`

---

## 替代提供商

`fast_apply` 和 `fast_search` 都可以使用 OpenAI 兼容提供商替代 Relace。

### 配置模式

```bash
# For fast_apply
export RELACE_APPLY_PROVIDER=openrouter
export RELACE_APPLY_API_KEY=sk-or-v1-xxx
export RELACE_APPLY_MODEL=anthropic/claude-3.5-sonnet

# For fast_search
export RELACE_SEARCH_PROVIDER=openai
export RELACE_SEARCH_API_KEY=sk-xxx
export RELACE_SEARCH_MODEL=gpt-4o
```

### API Key 解析顺序

1. `RELACE_APPLY_API_KEY` / `RELACE_SEARCH_API_KEY`（显式）
2. 提供商专用 key（如 `OPENROUTER_API_KEY`）
3. `RELACE_API_KEY`（仅限 `relace` 提供商）

### LSP 工具

`find_symbol` 工具使用 Language Server Protocol 进行 Python 语义查询：
- `definition`：跳转到符号定义
- `references`：查找符号的所有引用

> **注意：** 使用 `basedpyright`（随包安装）。首次调用会有 2-5 秒启动延迟。

### OpenAI Structured Outputs

使用 OpenAI 提供商且 `RELACE_SEARCH_TOOL_STRICT=1`（默认）时，并行工具调用会自动禁用。要启用并行调用：

```bash
export RELACE_SEARCH_TOOL_STRICT=0
export RELACE_SEARCH_PARALLEL_TOOL_CALLS=1
```

### Bash 工具

`bash` 工具默认禁用。在 Unix 上启用：

```json
{
  "mcpServers": {
    "relace": {
      "env": {
        "RELACE_SEARCH_ENABLED_TOOLS": "view_file,view_directory,grep_search,glob,find_symbol,bash"
      }
    }
  }
}
```

---

## 远程部署 (Streamable HTTP)

> **安全提示：** 本服务可读写文件。请勿直接暴露到公网。使用 `stdio`，或在 HTTP 前增加鉴权/VPN。

### 运行服务器

```bash
relace-mcp -t streamable-http --host 0.0.0.0 -p 8000
```

### 客户端配置

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

### CLI 选项

| 选项 | 默认值 | 描述 |
|------|--------|------|
| `--host` | `127.0.0.1` | 绑定地址 |
| `--port`, `-p` | `8000` | 端口号 |
| `--path` | `/mcp` | MCP 端点的 URL 路径 |
