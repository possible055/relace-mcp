# Benchmark 模块

> **注意**: 此模块正在开发中，API 和指标可能会变更。

使用 [MULocBench](https://github.com/MULocBench/MULocBench) 数据集评估 `fast_search` 性能。

## 1. 准备

**前置要求**: Python 3.11+、`git`、网络连接

**环境配置**（在项目根目录创建 `.env`）:
```bash
SEARCH_PROVIDER=relace          # 或: openai, openrouter
RELACE_API_KEY=your-key-here    # 或: OPENAI_API_KEY, OPENROUTER_API_KEY
```

**数据集**:

- **MULocBench**: 从 [MULocBench](https://github.com/MULocBench/MULocBench) 下载 → 放置于 `benchmark/artifacts/data/raw/mulocbench_v1.jsonl`
- **Loc-Bench (LocAgent)**: 通过 Hugging Face datasets-server 构建（无需 LocAgent）:
  ```bash
  uv run python -m benchmark.cli.build_locbench \
    --output artifacts/data/raw/locbench_v1.jsonl
  ```

## 2. 单次运行

```bash
# 基本运行
uv run python -m benchmark.cli.run --dataset artifacts/data/processed/elite_50.jsonl --limit 20

# 在 Loc-Bench 上运行（先执行 build_locbench）
uv run python -m benchmark.cli.run --dataset artifacts/data/raw/locbench_v1.jsonl --limit 20

# 带参数覆盖
uv run python -m benchmark.cli.run \
  --dataset artifacts/data/processed/elite_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --harness fast \
  --search-max-turns 8 \
  --search-temperature 0.2 \
  --no-progress

# Dual harness 额外控制
uv run python -m benchmark.cli.run \
  --harness dual \
  --dual-channel-turns 4 \
  --merger-temperature 0.1
```

**常用参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | 全部 | Case 数量 |
| `--shuffle/--no-shuffle` | `--shuffle` | 随机选择 |
| `--seed` | `0` | 随机种子 |
| `--harness` | `dual` | Harness 类型 (`fast` 或 `dual`) |
| `--search-max-turns` | env | 覆盖 `SEARCH_MAX_TURNS` |
| `--search-temperature` | env | 覆盖 `SEARCH_TEMPERATURE` |
| `--dual-channel-turns` | env | 覆盖 `SEARCH_DUAL_CHANNEL_TURNS` (仅 dual) |
| `--merger-temperature` | env | 覆盖 `MERGER_TEMPERATURE` (仅 dual) |
| `--search-prompt-file` | env | 覆盖 `SEARCH_PROMPT_FILE` (YAML) |
| `--progress/--no-progress` | `--progress` | 显示进度 |
| `--verbose` | 关闭 | 详细日志 |
| `--dry-run` | 关闭 | 仅预览 |

## 3. 网格搜索 (超参数调优)

运行 `turns × temperature` 笛卡尔积组合:

```bash
uv run python -m benchmark.cli.grid \
  --dataset artifacts/data/processed/elite_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --harness fast \
  --turns 4 --turns 6 --turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4 --temperatures 0.6

# Dual harness 额外维度
uv run python -m benchmark.cli.grid \
  --harness dual \
  --turns 4 --turns 8 \
  --temperatures 0 --temperatures 0.3 \
  --dual-channel-turns 2 --dual-channel-turns 4 \
  --merger-temperatures 0 --merger-temperatures 0.1
```

**网格参数**:
| 参数 | 必需 | 说明 |
|------|------|------|
| `--turns` | ✓ | `SEARCH_MAX_TURNS` 网格值 (可重复) |
| `--temperatures` | ✓ | `SEARCH_TEMPERATURE` 网格值 (可重复) |
| `--dual-channel-turns` | | `SEARCH_DUAL_CHANNEL_TURNS` 网格值 (可重复) |
| `--merger-temperatures` | | `MERGER_TEMPERATURE` 网格值 (可重复) |
| `--search-prompt-file` | | 覆盖所有 run 的提示文件 |
| `--output` | | 输出目录前缀 |
| `--dry-run` | | 仅打印计划的 run，不执行 |

**输出**: 网格摘要保存至 `artifacts/reports/<grid_name>.grid.json`

## 4. 分析结果

```bash
# 分析单次运行
uv run python -m benchmark.cli.analyze path/to/run.report.json

# 比较多次运行
uv run python -m benchmark.cli.analyze run1.report.json run2.report.json
```

## 5. 指标说明

| 指标 | 计算方式 |
|------|----------|
| File Recall | 找到的 GT 文件 / GT 文件总数 |
| File Precision | 正确文件 / 返回文件总数 |
| Line Coverage | 覆盖的 GT 行 / GT 行总数 |
| Line Precision | 正确行 / 返回行总数 |
| Line Prec(M) | 仅统计匹配文件：正确行 / 返回行总数 |
| Function Hit Rate | 有重叠的函数 / 函数总数 |

每个 `*.report.json` 包含 metadata 追踪: `temperature`、`max_turns`、`dual_channel_turns`、`prompt_file` 以确保可复现性。

## 6. 故障排除

| 问题 | 解决方案 |
|------|----------|
| 缺少 API key | 设置 `RELACE_API_KEY` 或对应 provider 的 key |
| 克隆失败 | 检查网络，确保 `git` 已安装 |
| 找不到数据集 | 将数据集放入 `benchmark/artifacts/data/` |
| 首次运行慢 | 正常—仓库首次下载后会缓存 |

## 目录结构

```
benchmark/
├── cli/
│   ├── run.py       # 单次运行 CLI
│   ├── grid.py      # 网格搜索 CLI
│   └── analyze.py   # 结果分析
├── datasets/        # 数据集加载器
├── evaluation/      # 指标实现
├── runner/          # 执行流程
├── artifacts/
│   ├── data/        # 数据集文件
│   ├── repos/       # 缓存仓库
│   ├── results/     # 运行输出 (.jsonl)
│   └── reports/     # 汇总报告 (.json)
```
