# Logging

File logging is opt-in. Set `MCP_LOGGING=safe` (with redaction) or `MCP_LOGGING=full` (no redaction).

## Log Location

| Platform | Path |
|----------|------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

## Log Format

Logs are written in JSON Lines (JSONL) format:

```json
{"kind":"apply_success","level":"info","trace_id":"a1b2c3d4","latency_ms":150,"file_path":"/path/to/file.py",...}
```

## Event Types

| Event Kind | Description |
|------------|-------------|
| `create_success` | New file created |
| `apply_success` | Edit applied successfully |
| `apply_error` | Edit failed |
| `search_start` | Search started |
| `search_turn` | Agent loop turn state |
| `tool_call` | Tool call with timing |
| `search_complete` | Search completed |
| `search_error` | Search failed |

## Cloud Event Types

| Event Kind | Description |
|------------|-------------|
| `cloud_sync_start` | Cloud sync started |
| `cloud_sync_complete` | Cloud sync completed |
| `cloud_sync_error` | Cloud sync failed |
| `cloud_search_start` | Cloud search started |
| `cloud_search_complete` | Cloud search completed |
| `cloud_search_error` | Cloud search failed |
| `cloud_info_start` | Cloud info started |
| `cloud_info_complete` | Cloud info completed |
| `cloud_info_error` | Cloud info failed |
| `cloud_list_start` | Cloud list started |
| `cloud_list_complete` | Cloud list completed |
| `cloud_list_error` | Cloud list failed |
| `cloud_clear_start` | Cloud clear started |
| `cloud_clear_complete` | Cloud clear completed |
| `cloud_clear_error` | Cloud clear failed |

## Log Rotation

- Rotates automatically at **10 MB**
- Keeps up to **5** rotated files
- Naming: `relace.YYYYMMDD_HHMMSS.log`
