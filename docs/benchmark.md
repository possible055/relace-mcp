# Benchmark Module

> **Note**: This module is under active development. APIs and metrics may change.

Evaluates `fast_search` performance using [MULocBench](https://github.com/MULocBench/MULocBench) dataset.

## 1. Setup

**Prerequisites**: Python 3.10+, `git`, network access

**Environment** (create `.env` in project root):
```bash
SEARCH_PROVIDER=relace          # or: openai, openrouter
RELACE_API_KEY=your-key-here    # or: OPENAI_API_KEY, OPENROUTER_API_KEY
```

**Dataset**: Download from [MULocBench](https://github.com/MULocBench/MULocBench) → place in `benchmark/data/mulocbench.jsonl`

## 2. Run Benchmark

```bash
# Basic run (5 cases, shuffled)
uv run python -m benchmark.cli

# More cases
uv run python -m benchmark.cli --limit 20

# Preview only (no search execution)
uv run python -m benchmark.cli --dry-run
```

**Key options**:
| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | `5` | Number of cases |
| `--shuffle/--no-shuffle` | `--shuffle` | Randomize selection |
| `--seed` | `0` | Random seed |
| `--output` | `results/benchmark_results.json` | Output path |
| `--progress/--no-progress` | `--progress` | Show progress bar |
| `--verbose` | off | Detailed logging |

<details>
<summary>All options</summary>

| Option | Default | Description |
|--------|---------|-------------|
| `--dataset` | `data/mulocbench.jsonl` | Dataset path |
| `--include-added-files` | off | Include newly added files |
| `--require-functions` | on | Require function-level ground truth |

</details>

## 3. Analyze Results

```bash
# Default results file
uv run python -m benchmark.analyze

# Specific file
uv run python -m benchmark.analyze path/to/results.json
```

Output includes: per-case table, metric distributions, worst-case identification.

## 4. Interpret Metrics

| Metric | Formula |
|--------|---------|
| File Recall | GT files found / Total GT files |
| File Precision | Correct files / Returned files |
| Line Coverage | GT lines covered / Total GT lines |
| Line Precision | Correct lines / Returned lines |
| Function Hit Rate | Functions with overlap / Total functions |

Results JSON structure: `metadata`, `total_cases`, `success_rate`, `avg_*`, `results[]`

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Missing API key | Set `RELACE_API_KEY` or provider-specific key |
| Clone fails | Check network, ensure `git` installed |
| Dataset not found | Place `mulocbench.jsonl` in `benchmark/data/` |
| Slow first run | Normal—repos cached after first download |

## Directory Structure

```
benchmark/
├── cli.py           # CLI entrypoint
├── analyze.py       # Result analysis
├── datasets/        # Dataset loaders
├── evaluation/      # Metrics implementation
├── run/             # Execution pipeline
├── data/            # Dataset files
├── repos/           # Cached repositories
└── results/         # Output JSON
```
