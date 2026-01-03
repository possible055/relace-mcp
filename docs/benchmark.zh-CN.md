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

**数据集**: 从 [MULocBench](https://github.com/MULocBench/MULocBench) 下载 → 放置于 `benchmark/data/mulocbench.jsonl`

## 2. 运行 Benchmark

```bash
# 基本运行 (5 个 case，随机打乱)
uv run python -m benchmark.cli

# 更多 case
uv run python -m benchmark.cli --limit 20

# 仅预览 (不执行搜索)
uv run python -m benchmark.cli --dry-run
```

**常用参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | `5` | Case 数量 |
| `--shuffle/--no-shuffle` | `--shuffle` | 随机选择 |
| `--seed` | `0` | 随机种子 |
| `--output` | `results/benchmark_results.json` | 输出路径 |
| `--progress/--no-progress` | `--progress` | 显示进度条 |
| `--verbose` | 关闭 | 详细日志 |

<details>
<summary>全部参数</summary>

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dataset` | `data/mulocbench.jsonl` | 数据集路径 |
| `--include-added-files` | 关闭 | 包含新增文件 |
| `--require-functions` | 开启 | 要求函数级 ground truth |

</details>

## 3. 分析结果

```bash
# 默认结果文件
uv run python -m benchmark.analyze

# 指定文件
uv run python -m benchmark.analyze path/to/results.json
```

输出包括：每 case 详细表格、指标分布、最差 case 识别。

## 4. 指标说明

| 指标 | 计算方式 |
|------|----------|
| File Recall | 找到的 GT 文件 / GT 文件总数 |
| File Precision | 正确文件 / 返回文件总数 |
| Line Coverage | 覆盖的 GT 行 / GT 行总数 |
| Line Precision | 正确行 / 返回行总数 |
| Line Prec(M) | 仅统计匹配文件：正确行 / 返回行总数 |
| Line IoU(M) | 仅统计匹配文件：交集 / 并集 |
| Function Hit Rate | 有重叠的函数 / 函数总数 |

结果 JSON 结构：`metadata`、`total_cases`、`success_rate`、`avg_*`、`results[]`

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| 缺少 API key | 设置 `RELACE_API_KEY` 或对应 provider 的 key |
| 克隆失败 | 检查网络，确保 `git` 已安装 |
| 找不到数据集 | 将 `mulocbench.jsonl` 放入 `benchmark/data/` |
| 首次运行慢 | 正常—仓库首次下载后会缓存 |

## 目录结构

```
benchmark/
├── cli.py           # CLI 入口
├── analyze.py       # 结果分析
├── datasets/        # 数据集加载器
├── evaluation/      # 指标实现
├── run/             # 执行流程
├── data/            # 数据集文件
├── repos/           # 缓存仓库
└── results/         # 输出 JSON
```
