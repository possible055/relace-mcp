# Benchmark 模块

> **注意**: 此模块正在开发中，API 和指标可能会变更。

Benchmark 模块使用 [MULocBench](https://github.com/MULocBench/MULocBench) 数据集评估 `fast_search` 的性能，该数据集提供 issue 到代码位置的映射。

## 目录结构

```
benchmark/
├── cli.py           # CLI 入口 (基于 click)
├── analyze.py       # 结果分析工具
├── paths.py         # Benchmark 路径辅助
├── datasets/        # 数据集加载器（如 MULocBench）
├── evaluation/      # 指标实现（paths/ranges/metrics）
├── run/             # 执行流水线（repo、metadata、runner）
├── data/            # 数据集文件 (mulocbench.jsonl)
├── repos/           # 缓存的 git 仓库
└── results/         # 基准测试输出 (JSON)
```

## 快速开始

```bash
# 使用默认参数运行 (5 个 case，随机打乱)
uv run python -m benchmark.cli

# 运行更多 case
uv run python -m benchmark.cli --limit 20

# 预览模式，不实际执行搜索
uv run python -m benchmark.cli --dry-run

# 分析结果
uv run python -m benchmark.analyze
```

## CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dataset` | `data/mulocbench.jsonl` | 数据集路径 |
| `--limit` | `5` | 最大运行 case 数 |
| `--shuffle/--no-shuffle` | `--shuffle` | 选择前是否打乱 |
| `--seed` | `0` | 随机种子 |
| `--include-added-files` | 关闭 | 包含新增文件 |
| `--require-functions` | 开启 | 要求函数级 ground truth |
| `--output` | `results/benchmark_results.json` | 输出路径 |
| `--verbose` | 关闭 | 详细日志 |
| `--progress/--no-progress` | `--progress` | 显示每个 case 的进度 |

## 指标说明

### 文件级别
- **File Recall**: 找到的 ground truth 文件数 / 总 ground truth 文件数
- **File Precision**: 正确文件数 / 返回文件总数
- **File F1**: Recall 与 Precision 的调和平均

### 行级别
- **Line Coverage**: 覆盖的 ground truth 行数 / 总 ground truth 行数
- **Line Precision**: 正确行数 / 返回行数总和
- **Line F1**: Line Coverage 与 Line Precision 的调和平均
- **Line Precision (Matched)**: 同上，但仅计算匹配文件
- **Line IoU (Matched)**: 匹配文件的交并比

### 函数级别
- **Function Hit Rate**: 有任意行重叠的函数数 / 目标函数总数

## 输出格式

结果以 JSON 格式保存，包含：
- `metadata`: 运行配置和环境信息
- `total_cases`, `success_rate`: 汇总统计
- `avg_*`: 所有 case 的平均指标
- `results`: 每个 case 的详细结果

当提供 `dataset_path` 时，`metadata.dataset` 也会包含数据集文件指纹信息：
- `dataset_path`, `dataset_bytes`, `dataset_sha256`

## 模块说明

### `datasets/mulocbench.py`
解析 MULocBench JSONL 格式为 `BenchmarkCase` 对象，包含：
- Query 文本 (issue 标题 + 正文)
- 仓库和 commit 信息
- Ground truth 文件/行范围
- 函数级目标

### `run/runner.py`
`BenchmarkRunner` 类负责：
- 仓库克隆和 checkout
- 调用 `fast_search`
- 计算每个 case 的指标
- 汇总统计

### `evaluation/metrics.py`
纯函数实现所有指标计算，处理路径规范化和范围合并。

### `analyze.py`
CLI 工具用于深入分析结果：
- 详细的每 case 表格
- 指标分布直方图
- 最差 case 识别
