# MCP Dashboard (仪表盘)

实时终端日志查看器，用于监控 `fast_apply` 和 `fast_search` 操作。

## 安装

Dashboard 需要 `textual` 库，包含在 `tools` 可选依赖中：

```bash
# 使用 pip
pip install relace-mcp[tools]

# 使用 uv
uv add relace-mcp --extra tools
```

## 快速开始

从终端启动 dashboard：

```bash
relace-dashboard
```

或通过 Python 模块：

```bash
python -m relace_mcp.dashboard
```

## 功能特性

### 1. 多视图标签页

Dashboard 提供五个不同的视图，可通过顶部的标签栏切换：

| 标签页 | 说明 | 快捷键 |
|--------|------|--------|
| **All** | 所有 `apply` 和 `search` 操作的事件 | 默认视图 |
| **Apply** | 仅文件创建和编辑事件 (`create_success`, `apply_success`, `apply_error`) | - |
| **Search** | 树形结构显示搜索会话、轮次和工具调用 | - |
| **Insights** | 工具使用统计与可视化柱状图 | - |
| **Errors** | 仅错误事件 (`apply_error`, `search_error`) | - |

### 2. 导航快捷键

| 按键 | 操作 |
|------|------|
| `←` / `h` | 上一个标签页 |
| `→` / `l` | 下一个标签页 |
| `t` | 切换时间范围 |
| `r` | 重新加载日志 |
| `q` | 退出 |

### 3. 时间范围筛选

点击 **Time** 按钮或按 `t` 切换时间范围：

- **1h** - 最近 1 小时
- **6h** - 最近 6 小时
- **24h** - 最近 24 小时（默认）
- **All** - 所有可用日志

### 4. 实时追踪

Dashboard 会自动追踪日志文件并实时显示新事件，无需手动刷新即可进行实时监控。

### 5. 统计信息头部

头部显示实时统计信息：

```
Total: 150 | Apply: 45✓ | Search: 12✓
```

## 视图详情

### All / Apply / Errors 视图

可滚动的日志视图，显示格式化的事件，包含：

- **时间戳** (HH:MM:SS)
- **事件类型标签**（颜色编码）
- **文件名**（针对 apply 操作）
- **Token 用量**（如有）
- **延迟时间**（秒）

输出示例：
```
09:15:32 APPLY  main.py tok:1234 (0.523s)
09:15:30 SEARCH "find auth handlers"
09:15:28 TOOL   grep_search (0.125s)
```

### Search 视图

以树形结构呈现搜索会话：

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

功能：
- **会话头部** 显示总轮次数、工具数、token 数、找到的文件数和总时间
- **轮次节点** 显示进度条、token 用量和 LLM 延迟
- **工具节点** 显示工具名称、成功状态和执行时间
- 为保持清晰，失败的工具调用会在此视图中隐藏

### Insights 视图

显示最近 100 次工具调用的汇总统计：

```
Tool Legend
├── █ grep (grep_search)
├── █ read (view_file)
└── █ apply (fast_apply)

Turn 1 [██████████████████████████████] (■ 60% grep, ■ 40% read)
Turn 2 [██████████████████████████████] (■ 70% read, ■ 30% grep)
```

功能：
- **颜色编码图例** 用于工具识别
- **堆叠柱状图** 显示每轮次的工具分布
- **切换按钮** 显示/隐藏失败的工具调用

## 日志文件位置

日志使用 `platformdirs` 存储：

| 平台 | 位置 |
|------|------|
| Linux | `~/.local/state/relace/relace.log` |
| macOS | `~/Library/Application Support/relace/relace.log` |
| Windows | `%LOCALAPPDATA%\relace\relace.log` |

## 事件类型

| 类型 | 说明 | 来源 |
|------|------|------|
| `create_success` | 新文件已创建 | `fast_apply` |
| `apply_success` | 文件编辑成功 | `fast_apply` |
| `apply_error` | 文件编辑失败 | `fast_apply` |
| `search_start` | 搜索会话开始 | `fast_search` |
| `search_turn` | LLM 轮次完成 | `fast_search` |
| `tool_call` | 搜索期间执行的工具 | `fast_search` |
| `search_complete` | 搜索会话完成 | `fast_search` |
| `search_error` | 搜索会话失败 | `fast_search` |

## 常见问题

### Dashboard 无法启动

```
Error: textual is not installed.
Install with: pip install relace-mcp[tools]
```

**解决方案：** 按照上述说明安装 `tools` 额外依赖。

### 没有显示日志

1. 确保你至少执行过一次 `fast_apply` 或 `fast_search`
2. 检查日志文件是否存在于预期位置
3. 尝试将时间范围筛选器调整为「All」

### 性能问题

对于非常大的日志文件：

1. 使用较窄的时间范围筛选（1h 或 6h）
2. Dashboard 每个视图限制显示 10,000 行
3. 搜索会话历史记录上限为 200 个会话
