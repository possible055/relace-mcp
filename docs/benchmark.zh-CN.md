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
  --search-max-turns 8 \
  --search-temperature 0.2 \
  --no-progress
```

**输出**:
- Results: `benchmark/artifacts/results/<name>.jsonl`
- Report: `benchmark/artifacts/reports/<name>.report.json`

**常用参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | 全部 | Case 数量 |
| `--shuffle/--no-shuffle` | `--shuffle` | 随机选择 |
| `--seed` | `0` | 随机种子 |
| `--search-max-turns` | env | 覆盖 `SEARCH_MAX_TURNS` |
| `--search-temperature` | env | 覆盖 `SEARCH_TEMPERATURE` |
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
  --turns 4 --turns 6 --turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4 --temperatures 0.6
```

**网格参数**:
| 参数 | 必需 | 说明 |
|------|------|------|
| `--turns` | ✓ | `SEARCH_MAX_TURNS` 网格值 (可重复) |
| `--temperatures` | ✓ | `SEARCH_TEMPERATURE` 网格值 (可重复) |
| `--search-prompt-file` | | 覆盖所有 run 的提示文件 |
| `--output` | | 输出目录前缀 |
| `--dry-run` | | 仅打印计划的 run，不执行 |

**输出**: 网格摘要保存至 `artifacts/reports/<grid_name>.grid.json`

## 4. 数据集验证

在运行 benchmark 前验证数据集的正确性:

```bash
# 验证默认数据集
uv run python -m benchmark.cli.validate

# 验证指定数据集
uv run python -m benchmark.cli.validate --input artifacts/data/raw/locbench_v1.jsonl

# 输出报告到文件
uv run python -m benchmark.cli.validate --output validation.json --verbose
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

## 5. 分析结果

```bash
# 分析单次运行
uv run python -m benchmark.cli.analyze path/to/run.report.json

# 比较多次运行
uv run python -m benchmark.cli.analyze run1.report.json run2.report.json
```

## 6. 指标说明

| 指标 | 计算方式 |
|------|----------|
| File Recall | 找到的 GT 文件 / GT 文件总数 |
| File Precision | 正确文件 / 返回文件总数 |
| Line Coverage | 覆盖的 GT 行 / GT 行总数 |
| Line Precision | 正确行 / 返回行总数 |
| Line Prec(M) | 仅统计匹配文件：正确行 / 返回行总数 |
| Function Hit Rate | 有重叠的函数 / 函数总数 |

每个 `*.report.json` 包含 metadata 追踪: `temperature`、`max_turns`、`prompt_file` 以确保可复现性。

## 7. 故障排除

| 问题 | 解决方案 |
|------|----------|
| 缺少 API key | 设置 `RELACE_API_KEY` 或对应 provider 的 key |
| 克隆失败 | 检查网络，确保 `git` 已安装 |
| 找不到数据集 | 将数据集放入 `benchmark/artifacts/data/` |
| 首次运行慢 | 正常—仓库首次下载后会缓存 |

## 8. 运行单元测试

```bash
uv run pytest benchmark/tests -v
```

## 目录结构

```
benchmark/
├── cli/
│   ├── run.py           # 单次运行 CLI
│   ├── grid.py          # 网格搜索 CLI
│   ├── analyze.py       # 结果分析
│   ├── validate.py      # 数据集验证
│   └── build_locbench.py  # Loc-Bench 构建
├── analysis/            # 分析工具 (function scope 等)
├── datasets/            # 数据集加载器
├── metrics/             # 指标实现
├── runner/              # 执行流程
├── tests/               # 单元测试
├── config.py            # 配置常量
├── schemas.py           # 数据结构定义
└── artifacts/           # (运行时生成，不在版控中)
    ├── data/            # 数据集文件
    ├── repos/           # 缓存仓库
    ├── results/         # 运行输出 (.jsonl)
    └── reports/         # 汇总报告 (.report.json, .grid.json)
```
