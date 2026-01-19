# Benchmark Module

> **Note**: This module is under active development. APIs and metrics may change.

Evaluates `fast_search` performance using [MULocBench](https://github.com/MULocBench/MULocBench) dataset.

## 1. Setup

**Prerequisites**: Python 3.11+, `git`, network access

**Environment** (create `.env` in project root):
```bash
SEARCH_PROVIDER=relace          # or: openai, openrouter
RELACE_API_KEY=your-key-here    # or: OPENAI_API_KEY, OPENROUTER_API_KEY
```

**Dataset**:

- **MULocBench**: Download from [MULocBench](https://github.com/MULocBench/MULocBench) → place in `benchmark/artifacts/data/raw/mulocbench_v1.jsonl`
- **Loc-Bench (LocAgent)**: Build from Hugging Face via datasets-server (no LocAgent required):
  ```bash
  uv run python -m benchmark.cli.build_locbench \
    --output artifacts/data/raw/locbench_v1.jsonl
  ```

## 2. Single Run

```bash
# Basic run
uv run python -m benchmark.cli.run --dataset artifacts/data/processed/elite_50.jsonl --limit 20

# Run on Loc-Bench (after build_locbench)
uv run python -m benchmark.cli.run --dataset artifacts/data/raw/locbench_v1.jsonl --limit 20

# With parameter overrides
uv run python -m benchmark.cli.run \
  --dataset artifacts/data/processed/elite_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --search-max-turns 8 \
  --search-temperature 0.2 \
  --no-progress
```

**Outputs**:
- Results: `benchmark/artifacts/results/<name>.jsonl`
- Report: `benchmark/artifacts/reports/<name>.report.json`

**Key options**:
| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | all | Number of cases |
| `--shuffle/--no-shuffle` | `--shuffle` | Randomize selection |
| `--seed` | `0` | Random seed |
| `--search-max-turns` | env | Override `SEARCH_MAX_TURNS` |
| `--search-temperature` | env | Override `SEARCH_TEMPERATURE` |
| `--search-prompt-file` | env | Override `SEARCH_PROMPT_FILE` (YAML) |
| `--progress/--no-progress` | `--progress` | Show progress |
| `--verbose` | off | Detailed logging |
| `--dry-run` | off | Preview only |

## 3. Grid Search (Hyperparameter Tuning)

Run Cartesian product of `turns × temperature` combinations:

```bash
uv run python -m benchmark.cli.grid \
  --dataset artifacts/data/processed/elite_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --turns 4 --turns 6 --turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4 --temperatures 0.6
```

**Grid options**:
| Option | Required | Description |
|--------|----------|-------------|
| `--turns` | ✓ | Grid values for `SEARCH_MAX_TURNS` (repeatable) |
| `--temperatures` | ✓ | Grid values for `SEARCH_TEMPERATURE` (repeatable) |
| `--search-prompt-file` | | Override prompt file for all runs |
| `--output` | | Output directory prefix |
| `--dry-run` | | Print planned runs without executing |

**Output**: Grid summary saved to `artifacts/reports/<grid_name>.grid.json`

## 4. Analyze Results

```bash
# Analyze single run
uv run python -m benchmark.cli.analyze path/to/run.report.json

# Compare multiple runs
uv run python -m benchmark.cli.analyze run1.report.json run2.report.json
```

## 5. Interpret Metrics

| Metric | Formula |
|--------|---------|
| File Recall | GT files found / Total GT files |
| File Precision | Correct files / Returned files |
| Line Coverage | GT lines covered / Total GT lines |
| Line Precision | Correct lines / Returned lines |
| Line Prec (Matched) | Correct lines / Returned lines (matched files only) |
| Function Hit Rate | Functions with overlap / Total functions |

Each `*.report.json` includes metadata tracking: `temperature`, `max_turns`, `prompt_file` for reproducibility.

## 6. Troubleshooting

| Problem | Solution |
|---------|----------|
| Missing API key | Set `RELACE_API_KEY` or provider-specific key |
| Clone fails | Check network, ensure `git` installed |
| Dataset not found | Place dataset in `benchmark/artifacts/data/` |
| Slow first run | Normal—repos cached after first download |

## Directory Structure

```
benchmark/
├── cli/
│   ├── run.py       # Single run CLI
│   ├── grid.py      # Grid search CLI
│   └── analyze.py   # Result analysis
├── datasets/        # Dataset loaders
├── evaluation/      # Metrics implementation
├── runner/          # Execution pipeline
├── artifacts/
│   ├── data/        # Dataset files
│   ├── repos/       # Cached repositories
│   ├── results/     # Run outputs (.jsonl)
│   └── reports/     # Summary reports (.report.json, .grid.json)
```
