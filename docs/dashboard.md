# MCP Dashboard

A real-time terminal-based log viewer for monitoring `fast_apply` and `agentic_search` operations.

Cloud tool events (`cloud_*`) also appear in the **All** and **Errors** views when `MCP_LOGGING=1`.

## Installation

The dashboard requires the `textual` library, which is included in the `tools` optional dependency:

```bash
# Using pip
pip install relace-mcp[tools]

# Using uv
uv add relace-mcp --extra tools
```

## Quick Start

Launch the dashboard from your terminal:

```bash
relogs
```

Or via Python module:

```bash
python -m relace_mcp.dashboard
```

## Features

### 1. Multi-View Tabs

The dashboard provides five different views accessible via the tab bar at the top:

| Tab | Description | Keyboard Shortcut |
|-----|-------------|-------------------|
| **All** | All log events (includes `apply`, `search`, and `cloud_*`) | Default view |
| **Apply** | Only file creation and editing events (`create_success`, `apply_success`, `apply_error`) | - |
| **Search** | Tree-structured view of search sessions with turns and tool calls | - |
| **Insights** | Aggregated tool usage statistics with visual bar charts | - |
| **Errors** | All error events (`*_error`, including `cloud_*_error`) | - |

### 2. Navigation

| Key | Action |
|-----|--------|
| `←` / `h` | Previous tab |
| `→` / `l` | Next tab |
| `t` | Cycle time range |
| `r` | Reload logs |
| `q` | Quit |

### 3. Time Range Filtering

Click the **Time** button or press `t` to cycle through time ranges:

- **1h** - Last 1 hour
- **6h** - Last 6 hours
- **24h** - Last 24 hours (default)
- **All** - All available logs

### 4. Real-Time Tailing

The dashboard automatically tails the log file and displays new events in real-time. No manual refresh is needed for live monitoring.

### 5. Statistics Header

The header displays live statistics:

```
Total: 150 | Apply: 45✓ | Search: 12✓
```

## View Details

### All / Apply / Errors View

A scrollable log view showing formatted events with:

- **Timestamp** (HH:MM:SS)
- **Event type badge** (color-coded)
- **File name** (for apply operations)
- **Token usage** (if available)
- **Latency** (in seconds)

Example output:
```
09:15:32 APPLY  main.py tok:1234 (0.523s)
09:15:30 SEARCH "find auth handlers"
09:15:28 TOOL   grep_search (0.125s)
```

### Search View

A tree-structured view organized by search session:

```
[09:15:30] (Turns: 3, Tools: 12, Tok: 5.2k, Files: 8, Time: 4.5s)
├── Query: find all authentication handlers
├── [████████░░░░] Turn 1/3 (1234 tok) (1.2s)
│   ├── grep_search ✓ (0.12s)
│   ├── view_file ✓ (0.08s)
│   └── view_file ✓ (0.05s)
├── [██████████░░] Turn 2/3 (2345 tok) (1.5s)
│   ├── grep_search ✓ (0.15s)
│   └── view_file ✓ (0.10s)
└── [████████████] Turn 3/3 (1500 tok) (1.8s)
    └── view_file ✓ (0.07s)
```

Features:
- **Session header** shows total turns, tools, tokens, files found, and total time
- **Turn nodes** show progress bar, token usage, and LLM latency
- **Tool nodes** show tool name, success status, and execution time
- Failed tool calls are hidden from this view for clarity

### Insights View

Displays aggregated tool usage statistics across the last 100 tool calls:

```
Tool Legend
├── █ grep (grep_search)
├── █ read (view_file)
└── █ apply (fast_apply)

Turn 1 [██████████████████████████████] (■ 60% grep, ■ 40% read)
Turn 2 [██████████████████████████████] (■ 70% read, ■ 30% grep)
```

Features:
- **Color-coded legend** for tool identification
- **Stacked bar chart** showing tool distribution per turn
- **Toggle button** to show/hide failed tool calls

## Log File Location

Logs are stored using `platformdirs`:

| Platform | Location |
|----------|----------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

## Event Types

| Kind | Description | Source |
|------|-------------|--------|
| `create_success` | New file created | `fast_apply` |
| `apply_success` | File edited successfully | `fast_apply` |
| `apply_error` | File edit failed | `fast_apply` |
| `search_start` | Search session started | `agentic_search` |
| `search_turn` | LLM turn completed | `agentic_search` |
| `tool_call` | Tool executed during search | `agentic_search` |
| `search_complete` | Search session completed | `agentic_search` |
| `search_error` | Search session failed | `agentic_search` |

### Cloud Events

Cloud operations emit structured events:

| Kind | Description | Source |
|------|-------------|--------|
| `cloud_sync_start` | Cloud sync started | `cloud_sync` |
| `cloud_sync_complete` | Cloud sync completed | `cloud_sync` |
| `cloud_sync_error` | Cloud sync failed | `cloud_sync` |
| `cloud_search_start` | Cloud search started | `cloud_search` |
| `cloud_search_complete` | Cloud search completed | `cloud_search` |
| `cloud_search_error` | Cloud search failed | `cloud_search` |
| `cloud_info_start` | Cloud info started | `cloud_info` |
| `cloud_info_complete` | Cloud info completed | `cloud_info` |
| `cloud_info_error` | Cloud info failed | `cloud_info` |
| `cloud_list_start` | Cloud list started | `cloud_list` |
| `cloud_list_complete` | Cloud list completed | `cloud_list` |
| `cloud_list_error` | Cloud list failed | `cloud_list` |
| `cloud_clear_start` | Cloud clear started | `cloud_clear` |
| `cloud_clear_complete` | Cloud clear completed | `cloud_clear` |
| `cloud_clear_error` | Cloud clear failed | `cloud_clear` |

## Troubleshooting

### Dashboard Won't Start

```
Error: textual is not installed.
Install with: pip install relace-mcp[tools]
```

**Solution:** Install the `tools` extra dependency as shown above.

### No Logs Displayed

1. Ensure you have run `fast_apply` or `agentic_search` at least once
2. Check that the log file exists at the expected location
3. Try adjusting the time range filter to "All"

### Performance Issues

For very large log files:

1. Use a narrower time range filter (1h or 6h)
2. The dashboard limits display to 10,000 lines per view
3. Search session history is capped at 200 sessions
