# Benchmark 模块

> **注意**: 此模块正在开发中，API 和指标可能会变更。

使用 Loc-Bench 数据集（源自 [LocAgent](https://github.com/IvanaXu/LocAgent)）评估 `agentic_search` 性能。

## 1. 准备

**前置要求**: Python 3.11+、`git`、网络连接

**执行方式**: `benchmark/` 是 repo 内部工具。请在仓库根目录使用 `uv run --extra benchmark ...` 运行。执行 benchmark 测试时，再额外加上 `--extra dev`。

**环境配置**（在项目根目录创建 `.env`）:
```bash
# Relace（默认）
SEARCH_PROVIDER=relace
RELACE_API_KEY=your-key-here

# OpenAI-compatible provider 示例
SEARCH_PROVIDER=openai
SEARCH_ENDPOINT=https://api.openai.com/v1
SEARCH_MODEL=gpt-4.1-mini
SEARCH_API_KEY=your-provider-key
```

对于非 Relace 提供商，benchmark 命令读取的是 `SEARCH_API_KEY`。`OPENAI_API_KEY`、`OPENROUTER_API_KEY` 这类提供商专用变量不会被自动加载。

`benchmark.cli.run` 和 `benchmark.cli.grid` 现在与 MCP server 共用同一套 runtime bootstrap。若设置了 `MCP_DOTENV_PATH`，会优先加载该文件；否则回退到默认的 dotenv 搜索路径。之后再应用 CLI 覆盖并刷新集中式 settings。实际优先级固定为：CLI flags > process env > dotenv values。

当 benchmark CLI 的路径参数不是绝对路径时，会按 `benchmark/` 作为基准目录解析。下面示例中的 `artifacts/...`，在磁盘上的实际位置就是 `benchmark/.data/...`。

**数据集**:

通过 Hugging Face datasets-server 构建 Loc-Bench（无需 LocAgent）:
```bash
uv run --extra benchmark python -m benchmark.cli.build_locbench \
  --output artifacts/data/raw/locbench_v1.jsonl
```

为可重复的 benchmark 运行生成一个处理后的子集:
```bash
uv run --extra benchmark python -m benchmark.cli.curate --count 50
```

如果使用 `--local-parquet`，请先在当前环境里安装 `pyarrow`。

## 2. 单次运行

```bash
# 在 curated 子集上基本运行
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/processed/curated_50.jsonl --limit 20

# 在 Loc-Bench 上运行（先执行 build_locbench）
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/raw/locbench_v1.jsonl --limit 20

# 带参数覆盖
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/processed/curated_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --max-turns 8 --temperature 0.2 -q

# 中断后从 checkpoint 恢复
uv run --extra benchmark python -m benchmark.cli.run \
  -o my_run --resume --timeout 300 --fail-fast 5
```

**输出**:
- Experiment root: `benchmark/.data/experiments/<experiment_name>/`
- Results: `benchmark/.data/experiments/<experiment_name>/results/results.jsonl`
- Report: `benchmark/.data/experiments/<experiment_name>/summary.json`
- Traces (启用 `--trace`): `benchmark/.data/experiments/<experiment_name>/traces/<case_id>.jsonl`
- Trace metadata (启用 `--trace`): `benchmark/.data/experiments/<experiment_name>/traces/<case_id>.meta.json`
- Events (启用 `--trace`): `benchmark/.data/experiments/<experiment_name>/traces/events.jsonl`

Run report 的 `metadata.artifacts` 也会写入 trace `schema_version`、`experiment_root`、`traces_dir` 与 `events_path`，方便机器消费这些 artifact。

默认 experiment 命名模板如下:
- `run--<dataset>--<search-mode>--<provider>--<timestamp>`
- `grid--<dataset>--<search-mode>--<provider>--avg-file-recall--<timestamp>`
- `trial--turns-<n>--temp-<value>`

**Trace 工作流**:
```bash
# 采集 raw trace 与 indexed retrieval hint metadata
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/processed/curated_50.jsonl \
  --limit 10 --trace --search-mode indexed

# 导出派生后的 search map JSON
uv run --extra benchmark python -m benchmark.cli.trace \
  --latest --search-map --json-out -o search-map.bundle.json

# 校验最新一轮 run 的 trace/meta/events 一致性
uv run --extra benchmark python -m benchmark.cli.trace \
  --latest --validate

# 对比单个 case 在多个 runs / grid trials 中的代码空间搜索轨迹
uv run --extra benchmark python -m benchmark.cli.case_map \
  benchmark/.data/experiments/run-a \
  benchmark/.data/experiments/run-b \
  --case-id case_1 --json-out -o case_1.compare.json
```

现在单次 run 的所有输出都会归档在同一个 experiment 目录下。`<case_id>.meta.json` 会保存该 case 的 retrieval metadata，包括外部索引 backend 返回的 `semantic_hints` 文件列表。Trace metadata 与 run-level events 都会带上 `schema_version` 字段，方便 consumer 做兼容性检查。

**常用参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dataset` | locbench_v1.jsonl | 数据集路径 |
| `-o, --output` | 自动 | Experiment 目录名/路径 |
| `--limit` | 全部 | Case 数量 |
| `--seed` | `0` | 随机种子 |
| `--shuffle` | 关闭 | 随机选择 |
| `--max-turns` | env | 覆盖 `SEARCH_MAX_TURNS` |
| `--temperature` | env | 覆盖 `SEARCH_TEMPERATURE` |
| `--prompt-file` | env | 覆盖 `SEARCH_PROMPT_FILE` (YAML) |
| `--timeout` | 无 | 单个 case 超时秒数 |
| `--fail-fast` | 无 | 连续 N 次失败后停止 |
| `--resume` | 关闭 | 从 checkpoint 恢复 |
| `-v, --verbose` | 关闭 | 详细日志 |
| `-q, --quiet` | 关闭 | 禁用进度条 |
| `--dry-run` | 关闭 | 仅预览 |
| `--trace` | 关闭 | 保存逐 case trace JSONL 和 run 级别 events JSONL |

**搜索模式**:
- `agentic` 是默认模式，不依赖 retrieval index。
- `indexed` 需要可用的 retrieval backend，以及每个 repo 对应的最新本地 index 或 cloud sync state。

## 3. 网格搜索 (超参数调优)

运行 `turns × temperature` 笛卡尔积组合:

```bash
uv run --extra benchmark python -m benchmark.cli.grid \
  --dataset artifacts/data/processed/curated_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --max-turns 4 --max-turns 6 --max-turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4 --temperatures 0.6
```

**网格参数**:
| 参数 | 必需 | 说明 |
|------|------|------|
| `--max-turns` | ✓ | `SEARCH_MAX_TURNS` 网格值 (可重复) |
| `--temperatures` | ✓ | `SEARCH_TEMPERATURE` 网格值 (可重复) |
| `--prompt-file` | | 覆盖所有 run 的 `SEARCH_PROMPT_FILE` |
| `--output` | | Grid experiment 目录 |
| `--dry-run` | | 仅打印计划的 run，不执行 |

**输出**: Grid parent 摘要保存至 `benchmark/.data/experiments/<grid_name>/summary.json`

## 4. 数据集验证

在运行 benchmark 前验证数据集的正确性:

```bash
# 验证默认数据集
uv run --extra benchmark python -m benchmark.cli.validate

# 验证指定数据集
uv run --extra benchmark python -m benchmark.cli.validate --input artifacts/data/raw/locbench_v1.jsonl

# 输出报告到文件
uv run --extra benchmark python -m benchmark.cli.validate --output validation.json --verbose
```

**验证项目**:
- `hard_gt` / `soft_context` 文件是否存在
- 行号范围是否有效
- 函数名是否与 AST 解析结果匹配
- `target_ranges` 是否在 context range 内
- solvability evidence 是否出现在 query 中

**参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | `locbench_v1.jsonl` | 数据集路径 |
| `--output` | stdout | 报告输出路径 |
| `--limit` | 全部 | 验证数量 |
| `-v/--verbose` | 关闭 | 详细输出 |

## 5. 分析与报告

```bash
# 分析单次运行 (详细 stdout)
uv run --extra benchmark python -m benchmark.cli.analyze \
  path/to/experiment/summary.json

# 比较多个 report 文件 (Markdown 输出)
uv run --extra benchmark python -m benchmark.cli.report \
  path/to/run-a/summary.json \
  path/to/run-b/summary.json

# 从 grid parent summary 找最佳配置
uv run --extra benchmark python -m benchmark.cli.report --best \
  path/to/grid-experiment/summary.json

# 分析 result 文件中的失败 / 未完成 case
uv run --extra benchmark python -m benchmark.cli.report --failures \
  path/to/experiment/results/results.jsonl

# 输出比较报告到文件
uv run --extra benchmark python -m benchmark.cli.report -o comparison.md *.report.json

# 对比一个 case 在 grid trials 之间的代码空间 map
uv run --extra benchmark python -m benchmark.cli.case_map \
  path/to/grid-experiment/summary.json \
  --case-id case_1 -o case_1.compare.md

# 启动本地 benchmark web analyzer
uv run --extra benchmark --extra benchmark-web python -m benchmark.cli.web
```

**各模式接受的输入**:
- Comparison mode: 一个或多个非 grid 的 `*.report.json`
- `--best`: 恰好一个 grid `summary.json`
- `--failures`: 恰好一个 `*.jsonl`

## 6. 指标说明

| 指标 | 计算方式 |
|------|----------|
| File Recall | 找到的 GT 文件 / GT 文件总数 |
| File Precision | 正确文件 / 返回文件总数 |
| Line Coverage | 覆盖的 GT 行 / GT 行总数 |
| Line Prec(M) | 仅统计匹配文件：正确行 / 返回行总数 |
| Function Hit Rate | 有重叠的函数 / 函数总数 |

每个 `summary.json` 都包含可复现所需的 metadata。Grid parent report 另外会带 `metadata.experiment.type = "grid"`，以及包含 `search_space`、`trials`、`best_trial` 的 `grid` 区块。

## 6.1 Web Analyzer

benchmark web analyzer 是一个本地 SPA + Python API，用来浏览 experiments，并对比同一个 `case_id` 在不同 runs 之间的代码空间搜索轨迹。

```bash
# 终端 1: Python API + static app server
uv run --extra benchmark --extra benchmark-web python -m benchmark.cli.web

# 终端 2: frontend dev server
cd benchmark/viewer/frontend
npm ci
npm run dev
```

Web app 默认读取 `benchmark/.data/experiments/` 下的 benchmark artifacts，并以派生后的 `search-map.bundle.json` / `case comparison analysis` 作为唯一分析数据源。

## 7. 故障排除

| 问题 | 解决方案 |
|------|----------|
| 缺少 benchmark 依赖 | 使用 `uv run --extra benchmark ...` 运行命令 |
| 缺少 API key | Relace 模式设置 `RELACE_API_KEY`；非 Relace 模式设置 `SEARCH_PROVIDER`、`SEARCH_ENDPOINT`、`SEARCH_MODEL` 与 `SEARCH_API_KEY` |
| 克隆失败 | 检查网络，确保 `git` 已安装 |
| `indexed` preflight 失败 | 确认 retrieval backend 可用，且 index / cloud sync state 是最新的 |
| 找不到数据集 | 将数据集放入 `benchmark/.data/datasets/` |
| 首次运行慢 | 正常—仓库首次下载后会缓存 |

## 8. 运行单元测试

```bash
uv run --extra dev --extra benchmark pytest benchmark/tests -q
```

Web analyzer backend 测试:

```bash
uv run --extra dev --extra benchmark --extra benchmark-web pytest benchmark/tests/web -q
```

这组测试只覆盖 benchmark 子系统，不包含在仓库默认 `pytest` testpaths 里。CI 会用单独的 Ubuntu / Python 3.13 benchmark job 持续执行它们。

## 目录结构

```
benchmark/
├── config/             # benchmark 内部配置
│   ├── paths.py         # 目录/路径 helper 与默认数据集路径
│   └── settings.py      # benchmark 内部设置（如 EXCLUDED_REPOS）
├── cli/
│   ├── run.py           # 单次运行 CLI
│   ├── grid.py          # 网格搜索 CLI
│   ├── report.py        # 报告生成
│   ├── analyze.py       # 详细分析
│   ├── curate.py        # 数据集筛选
│   ├── validate.py      # 数据集验证
│   └── build_locbench.py  # Loc-Bench 构建
├── analysis/            # 分析工具 (function scope 等)
├── viewer/             # Benchmark 结果查看器（FastAPI + React SPA）
├── frontend/            # benchmark SPA 前端（仅 repo-local）
├── datasets/            # 数据集加载器
├── metrics/             # 指标实现
├── experiments/              # 执行流程
│   └── experiment_paths.py  # experiment 命名与产物布局 helper
├── tests/
│   ├── analysis/
│   ├── cli/
│   ├── datasets/
│   ├── docs/
│   └── experiments/
├── schemas.py           # 数据结构定义
└── artifacts/           # (运行时生成，不在版控中)
    ├── data/            # 数据集文件
    ├── experiments/     # 按 experiment 归档的输出
    │   └── <experiment_name>/
    │       ├── events/  # Run 级别 events (.jsonl)
    │       ├── analysis/ # 派生分析产物 (search-map.bundle.json)
    │       ├── results/ # 运行输出 (.jsonl)
    │       ├── trials/    # 仅 grid child trial 使用
    │       └── traces/  # 逐 case traces (.jsonl + .meta.json)
    ├── repos/           # 缓存仓库
```
