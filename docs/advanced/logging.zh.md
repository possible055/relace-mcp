# 日志

文件日志为可选功能。设置 `MCP_LOGGING=safe`（启用并遮蔽敏感内容）或 `MCP_LOGGING=full`（启用不遮蔽）。

## 日志位置 {#log-location}

| 平台 | 路径 |
|------|------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

## 日志格式 {#log-format}

日志以 JSON Lines (JSONL) 格式写入：

```json
{"kind":"apply_success","level":"info","trace_id":"a1b2c3d4","latency_ms":150,"file_path":"/path/to/file.py",...}
```

## 事件类型 {#event-types}

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

## Cloud 事件类型 {#cloud-event-types}

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

## 日志轮转 {#log-rotation}

- 超过 **10 MB** 时自动轮转
- 最多保留 **5** 个轮转文件
- 命名格式：`relace.YYYYMMDD_HHMMSS.log`
