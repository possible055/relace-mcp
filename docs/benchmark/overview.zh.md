# Benchmark

使用 [Loc-Bench](https://github.com/gersteinlab/LocAgent) 数据集评估 `agentic_search` 与 `agentic_retrieval` 的代码定位准确性。Loc-Bench 是一组来自真实开源仓库的代码搜索任务。

!!! warning "开发中"
    API 与指标定义可能变更。

## 概述

基准测试衡量搜索工具根据自然语言查询**定位相关代码**的能力。每个测试用例包含：

- **查询**：描述需要查找的内容（例如 "where is authentication handled"）
- **Ground Truth**：应当返回的准确文件、行范围和函数
- **仓库**：固定到特定 commit 以确保可复现

评估产出文件级、行级和函数级指标，量化 **Recall**（是否找到了重要内容）和 **Precision**（是否避免了噪声）。

## 前置条件

| 需求 | 说明 |
|------|------|
| Python | 3.12+（由 `uv` 管理） |
| Git | 用于克隆评估仓库 |
| API Key | `.env` 中的 `RELACE_API_KEY` 或其他 provider 对应的 key |
| 磁盘空间 | ~2 GB（缓存仓库存于 `artifacts/repos/`） |

在项目根目录创建 `.env`：

```bash
SEARCH_PROVIDER=relace    # 可选: relace, openai, openrouter
RELACE_API_KEY=<key>      # 对应 provider 的 API key
```

## 快速开始

```bash
# 1. 构建数据集
uv run python -m benchmark.cli.build_locbench \
  --output artifacts/data/raw/locbench_v1.jsonl

# 2. 执行评估
uv run python -m benchmark.cli.run \
  --dataset artifacts/data/raw/locbench_v1.jsonl \
  --limit 50

# 3. 分析结果
uv run python -m benchmark.cli.analyze artifacts/reports/<name>.report.json
```

## 工作流

典型的基准测试流程分为三个阶段：

### 1. 构建数据集

将上游 Loc-Bench 数据转换为内部 JSONL 格式：

```bash
uv run python -m benchmark.cli.build_locbench \
  --output artifacts/data/raw/locbench_v1.jsonl
```

可选：验证数据集以检查 ground truth 完整性：

```bash
uv run python -m benchmark.cli.validate --input artifacts/data/raw/locbench_v1.jsonl
```

验证项目包括：文件存在性、行号范围有效性、函数名称 AST 匹配、`target_ranges` 在 context range 内。

### 2. 执行评估

执行单次评估：

```bash
uv run python -m benchmark.cli.run \
  --dataset artifacts/data/raw/locbench_v1.jsonl \
  --limit 50 --shuffle
```

或使用网格搜索遍历超参数组合：

```bash
uv run python -m benchmark.cli.grid \
  --dataset artifacts/data/processed/elite_50.jsonl \
  --limit 50 --shuffle \
  --max-turns 4 --max-turns 6 --max-turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4
```

每次运行产出两个文件：

| 文件 | 内容 |
|------|------|
| `artifacts/results/<name>.jsonl` | 逐用例详细结果 |
| `artifacts/reports/<name>.report.json` | 汇总报告 |

### 3. 分析结果

```bash
# 单次运行 — 详细分析
uv run python -m benchmark.cli.analyze path/to/run.report.json

# 多次运行对比
uv run python -m benchmark.cli.report run1.report.json run2.report.json

# 从网格搜索中查找最佳配置
uv run python -m benchmark.cli.report --best grid.grid.json
```

## CLI 参考

### `run` — 单次评估

```bash
uv run python -m benchmark.cli.run [OPTIONS]
```

| 参数 | 说明 |
|------|------|
| `--dataset PATH` | 数据集 JSONL 路径 |
| `-o, --output PREFIX` | 输出文件前缀（默认：自动生成含时间戳） |
| `--limit N` | 最大评估用例数 |
| `--shuffle` | 随机抽样 |
| `--seed N` | 随机种子（默认: `0`） |
| `--max-turns N` | 覆写 `SEARCH_MAX_TURNS` |
| `--temperature F` | 覆写 `SEARCH_TEMPERATURE` |
| `--search-mode MODE` | `agentic`（默认）或 `indexed` |
| `--lsp-tools MODE` | LSP 工具: `true`、`false` 或 `auto` |
| `--enabled-tools LIST` | 逗号分隔的启用工具列表 |
| `--prompt-file PATH` | 覆写 `SEARCH_PROMPT_FILE`（YAML） |
| `--timeout N` | 单用例超时秒数 |
| `--fail-fast N` | 连续 N 次失败后停止 |
| `--resume` | 从 checkpoint 恢复 |
| `--dry-run` | 仅加载数据，不执行搜索 |
| `-v, --verbose` | 详细输出 |
| `-q, --quiet` | 禁用进度条 |

### `grid` — 超参数网格搜索

执行 `max_turns × temperature` 的笛卡尔积组合：

```bash
uv run python -m benchmark.cli.grid [OPTIONS]
```

接受 `run` 的所有参数，外加：

| 参数 | 说明 |
|------|------|
| `--max-turns N` | 一个或多个 turn 数（可重复） |
| `--temperatures F` | 一个或多个 temperature 值（可重复） |

**输出**: `artifacts/reports/<grid_name>.grid.json`

### `validate` — 数据集验证

```bash
uv run python -m benchmark.cli.validate --input <dataset.jsonl>
```

验证项目：

- Ground truth 文件在目标仓库中的存在性
- 行号范围有效性
- 函数名称与 AST 解析匹配
- `target_ranges` 在 context range 范围内

### `analyze` / `report` — 结果分析

```bash
uv run python -m benchmark.cli.analyze <report.json>
uv run python -m benchmark.cli.report <run1.json> <run2.json> [...]
uv run python -m benchmark.cli.report --best <grid.json>
```

## 评估指标

### 文件级指标

**File Recall** — 找到了多少比例的 ground truth 文件？

$$\text{File Recall} = \frac{|\text{returned files} \cap \text{GT files}|}{|\text{GT files}|}$$

Recall 为 **1.0** 表示所有相关文件都包含在结果中。

**File Precision** — 返回的文件中有多少是真正相关的？

$$\text{File Precision} = \frac{|\text{returned files} \cap \text{GT files}|}{|\text{returned files}|}$$

Precision 为 **1.0** 表示没有返回无关文件。

### 行级指标

**Line Coverage** — Ground truth 行被返回范围覆盖了多少？

$$\text{Line Coverage} = \frac{|\text{returned lines} \cap \text{GT lines}|}{|\text{GT lines}|}$$

**Line Precision (Matched)** — 在匹配的文件中，返回的行范围有多精确？

$$\text{Line Precision}_M = \frac{|\text{correct lines in matched files}|}{|\text{returned lines in matched files}|}$$

此指标仅限于**匹配的文件**，以避免对文件级未命中的双重惩罚。

### 函数级指标

**Function Hit Rate** — 多少 ground truth 函数有重叠覆盖？

$$\text{Function Hit Rate} = \frac{\text{functions with overlap}}{\text{total GT functions}}$$

当任意返回的行范围与函数定义重叠时，该函数视为"命中"。

### Quality Score

用于快速比较的单一综合指标：

$$\text{Quality Score} = 0.4 \times \text{File Recall} + 0.4 \times \text{Line Precision}_M + 0.2 \times \text{Function Hit Rate}$$

## 解读结果

运行基准测试后，`.report.json` 文件包含汇总统计。以下是一个示例：

```json
{
  "total_cases": 50,
  "avg_file_recall": 0.72,
  "avg_file_precision": 0.65,
  "avg_line_coverage": 0.58,
  "avg_line_precision_matched": 0.71,
  "avg_function_hit_rate": 0.64,
  "avg_quality_score": 0.67,
  "avg_latency_ms": 3200,
  "avg_turns_used": 4.2
}
```

**如何解读：**

- **File Recall 0.72** — 搜索找到了 72% 的应返回文件。大部分相关文件已被覆盖，但仍有提升空间。
- **Line Precision (M) 0.71** — 在找对文件的情况下，71% 的返回行是真正相关的。越高越好；低于 0.5 说明返回范围过宽。
- **Quality Score 0.67** — 综合指标。跨运行比较此值以衡量整体改进。
- **Latency 3200 ms** — 单用例平均耗时。用于发现超时问题。
- **Turns 4.2** — 平均 agentic search 迭代次数。更多 turn 通常提高 recall，但增加延迟。

### 参考基准

以下为粗略参考值，实际目标取决于具体使用场景：

| 指标 | 基线 | 良好 | 优秀 |
|------|------|------|------|
| File Recall | 0.50 | 0.70 | 0.85+ |
| File Precision | 0.40 | 0.60 | 0.75+ |
| Line Coverage | 0.30 | 0.55 | 0.70+ |
| Line Precision (M) | 0.40 | 0.65 | 0.80+ |
| Function Hit Rate | 0.35 | 0.60 | 0.75+ |
| Quality Score | 0.40 | 0.65 | 0.80+ |

!!! tip
    使用 `--max-turns` 和 `--temperature` 在延迟与准确性之间权衡。更多 turn 通常提高 recall；更低的 temperature 提高 precision。

## 疑难排解

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| API key 错误 | `.env` 中的 key 缺失或无效 | 检查 `RELACE_API_KEY` 或对应 provider 的 key |
| 克隆失败 | 网络问题或缺少 `git` | 确认网络连接；确保 `git` 已安装 |
| 首次运行缓慢 | 仓库首次克隆中 | 正常 — 后续运行将使用 `artifacts/repos/` 中的缓存 |
| 内存不足 | 加载的用例过多 | 使用 `--limit` 减少用例数 |
| 超时错误 | 用例超出单用例时间限制 | 增大 `--timeout` 或检查 API 响应速度 |
| 结果不一致 | LLM 输出的非确定性 | 设置 `--temperature 0` 并固定 `--seed` 以确保可复现 |
| Resume 不生效 | 缺少 checkpoint 文件 | 确保前次运行写入了相同的输出路径 |

## 运行测试

```bash
uv run pytest benchmark/tests -v
```
