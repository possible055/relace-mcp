# Benchmark Module

> **Note**: This module is under active development. APIs and metrics may change.

The benchmark module evaluates `fast_search` performance using the [MULocBench](https://github.com/MULocBench/MULocBench) dataset, which provides issue-to-code-location mappings.

## Directory Structure

```
benchmark/
├── cli.py           # CLI entrypoint (click-based)
├── analyze.py       # Result analysis utilities
├── paths.py         # Benchmark path helpers
├── datasets/        # Dataset loaders (e.g., MULocBench)
├── evaluation/      # Metric implementations (paths/ranges/metrics)
├── run/             # Execution pipeline (repo, metadata, runner)
├── data/            # Dataset files (mulocbench.jsonl)
├── repos/           # Cached git repositories
└── results/         # Benchmark output (JSON)
```

## Quick Start

```bash
# Run benchmark with defaults (5 cases, shuffled)
uv run python -m benchmark.cli

# Run with more cases
uv run python -m benchmark.cli --limit 20

# Dry run to preview cases
uv run python -m benchmark.cli --dry-run

# Analyze results
uv run python -m benchmark.analyze
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--dataset` | `data/mulocbench.jsonl` | Dataset path |
| `--limit` | `5` | Max cases to run |
| `--shuffle/--no-shuffle` | `--shuffle` | Shuffle before selecting |
| `--seed` | `0` | Random seed |
| `--include-added-files` | off | Include newly added files |
| `--require-functions` | on | Require function-level ground truth |
| `--output` | `results/benchmark_results.json` | Output path |
| `--verbose` | off | Verbose logging |
| `--progress/--no-progress` | `--progress` | Show per-case progress |

## Metrics

### File-Level
- **File Recall**: Ground truth files found / Total ground truth files
- **File Precision**: Correct files / Total returned files
- **File F1**: Harmonic mean of recall & precision

### Line-Level
- **Line Coverage**: Ground truth lines covered / Total ground truth lines
- **Line Precision**: Correct lines / Total returned lines
- **Line F1**: Harmonic mean of Line Coverage & Line Precision
- **Line Precision (Matched)**: Same as above, but only for matched files
- **Line IoU (Matched)**: Intersection over Union for matched files

### Function-Level
- **Function Hit Rate**: Functions with any line overlap / Total target functions

## Output Format

Results are saved as JSON with:
- `metadata`: Run configuration and environment info
- `total_cases`, `success_rate`: Aggregate stats
- `avg_*`: Averaged metrics across all cases
- `results`: Per-case detailed results

`metadata.dataset` also includes a dataset file fingerprint when `dataset_path` is provided:
- `dataset_path`, `dataset_bytes`, `dataset_sha256`

## Modules

### `datasets/mulocbench.py`
Parses MULocBench JSONL format into `BenchmarkCase` objects containing:
- Query text (issue title + body)
- Repository and commit info
- Ground truth file/line ranges
- Function-level targets

### `run/runner.py`
`BenchmarkRunner` class handles:
- Repository cloning and checkout
- `fast_search` invocation
- Metric computation per case
- Summary aggregation

### `evaluation/metrics.py`
Pure functions for computing all metrics. Handles path normalization and range merging.

### `analyze.py`
CLI tool for deeper result analysis:
- Detailed per-case table
- Metric distribution histograms
- Worst-case identification
