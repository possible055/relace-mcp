# 高级用法

本文档涵盖面向高级用户和开发者的高级配置选项。

## 目录

- [环境变量](environment-variables.md)
- [使用 .env 文件](#using-a-env-file)
- [同步模式](#sync-modes)
- [日志](#logging)
- [替代提供商](#alternative-providers)
- [远程部署 (Streamable HTTP)](#remote-deployment-streamable-http)

---

## 使用 .env 文件 {#using-a-env-file}

可以使用集中的 `.env` 文件代替在 MCP 配置中设置多个环境变量：

```bash
# ~/.config/relace/.env
RELACE_API_KEY=rlc-your-api-key

# 自定义搜索模型（可选）
SEARCH_PROVIDER=openai
SEARCH_ENDPOINT=https://api.openai.com/v1
SEARCH_MODEL=gpt-4o
SEARCH_API_KEY=sk-xxx

# 其他设置
MCP_LOGGING=safe
SEARCH_MAX_TURNS=6
```

然后在 MCP 配置中指向该文件：

```json
{
  "mcpServers": {
    "relace": {
      "command": "uv",
      "args": ["tool", "run", "relace-mcp"],
      "env": {
        "MCP_DOTENV_PATH": "~/.config/relace/.env"
      }
    }
  }
}
```

> **注意：** 直接在 `env` 中设置的变量优先于 `.env` 文件中的变量。

---

## 同步模式 {#sync-modes}

`cloud_sync` 工具支持三种同步模式：

| 模式 | 触发条件 | 描述 |
|------|----------|------|
| 增量同步 | (默认) | 仅上传新增/修改的文件，删除已移除的文件 |
| 安全完整同步 | `force=True`、首次同步或 HEAD 变更 | 上传所有文件；除非 HEAD 变更，否则抑制删除 |
| 镜像完整同步 | `force=True, mirror=True` | 完全覆盖云端以匹配本地 |

当 git HEAD 自上次同步后发生变化（如分支切换、rebase），安全完整同步模式会自动清理旧 ref 的僵尸文件。

---

## 日志 {#logging}

文件日志为可选功能。设置 `MCP_LOGGING=safe`（启用并遮蔽敏感内容）或 `MCP_LOGGING=full`（启用不遮蔽）。

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

### Cloud 事件类型

| 事件类型 | 描述 |
|----------|------|
| `cloud_sync_start` | Cloud 同步开始 |
| `cloud_sync_complete` | Cloud 同步完成 |
| `cloud_sync_error` | Cloud 同步失败 |
| `cloud_search_start` | Cloud 搜索开始 |
| `cloud_search_complete` | Cloud 搜索完成 |
| `cloud_search_error` | Cloud 搜索失败 |
| `cloud_info_start` | Cloud 信息查询开始 |
| `cloud_info_complete` | Cloud 信息查询完成 |
| `cloud_info_error` | Cloud 信息查询失败 |
| `cloud_list_start` | Cloud 列表开始 |
| `cloud_list_complete` | Cloud 列表完成 |
| `cloud_list_error` | Cloud 列表失败 |
| `cloud_clear_start` | Cloud 清理开始 |
| `cloud_clear_complete` | Cloud 清理完成 |
| `cloud_clear_error` | Cloud 清理失败 |

### 日志轮转

- 超过 **10 MB** 时自动轮转
- 最多保留 **5** 个轮转文件
- 命名格式：`relace.YYYYMMDD_HHMMSS.log`

---

## 替代提供商 {#alternative-providers}

`fast_apply` 和 `agentic_search` 都可以使用 OpenAI 兼容提供商替代 Relace。

### 配置模式

```bash
# For fast_apply
export APPLY_PROVIDER=openrouter
export APPLY_API_KEY=[REDACTED:api-key]
export APPLY_MODEL=anthropic/claude-3.5-sonnet

# For agentic_search
export SEARCH_PROVIDER=openai
export SEARCH_API_KEY=[REDACTED:api-key]
export SEARCH_MODEL=gpt-4o
```

### API Key 解析顺序

1. `APPLY_API_KEY` / `SEARCH_API_KEY`（显式）
2. 提供商专用 key（如 `OPENROUTER_API_KEY`）
3. `RELACE_API_KEY`（仅限 `relace` 提供商）

### LSP 工具

LSP 工具（`find_symbol`、`search_symbol`、`get_type`、`list_symbols`、`call_graph`）默认禁用。可通过以下方式启用：

- **自动检测：** `SEARCH_LSP_TOOLS=auto` — 仅启用已安装服务器的语言
- **全部启用：** `SEARCH_LSP_TOOLS=1` — 一次启用所有 LSP 工具
- **精细控制：** `SEARCH_LSP_TOOLS=1` + `SEARCH_ENABLED_TOOLS=view_file,find_symbol,...` — 仅启用列表中的 LSP 工具

> **注意：** `SEARCH_LSP_TOOLS` 作为**门控开关**。为 `false`（默认）时，LSP 工具始终禁用。为 `auto` 时，仅启用已安装服务器对应的语言。为 `true` 时，默认启用所有 LSP 工具，或由允许列表过滤。

`find_symbol` 工具使用 Language Server Protocol 进行 Python 语义查询：
- `definition`：跳转到符号定义
- `references`：查找符号的所有引用

> **注意：** 使用 `basedpyright`（随包安装）。首次调用会有 2-5 秒启动延迟。

### OpenAI Structured Outputs

使用 OpenAI 提供商且 `SEARCH_TOOL_STRICT=1`（默认）时，并行工具调用会自动禁用。要启用并行调用：

```bash
export SEARCH_TOOL_STRICT=0
export SEARCH_PARALLEL_TOOL_CALLS=1
```

### Bash 工具

`bash` 工具默认禁用。在 Unix 上启用：

```json
{
  "mcpServers": {
    "relace": {
      "env": {
        "SEARCH_ENABLED_TOOLS": "view_file,view_directory,grep_search,glob,find_symbol,bash"
      }
    }
  }
}
```

---

## 远程部署 (Streamable HTTP) {#remote-deployment-streamable-http}

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
