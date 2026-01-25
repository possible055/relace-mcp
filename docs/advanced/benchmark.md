# Benchmark Module

> **Note**: This module is under active development. APIs and metrics may change.

Evaluates `agentic_search` performance using the Loc-Bench dataset (derived from [LocAgent](https://github.com/gersteinlab/LocAgent)).

## 1. Setup

**Prerequisites**: Python 3.11+, `git`, network access

**Environment** (create `.env` in project root):
```bash
SEARCH_PROVIDER=relace          # or: openai, openrouter
RELACE_API_KEY=your-key-here    # or: OPENAI_API_KEY, OPENROUTER_API_KEY
```

**Dataset**:

Build the Loc-Bench dataset from Hugging Face via datasets-server (no LocAgent required):
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
  --max-turns 8 --temperature 0.2 -q

# Resume from checkpoint after interruption
uv run python -m benchmark.cli.run \
  -o my_run --resume --timeout 300 --fail-fast 5
```

**Outputs**:
- Results: `benchmark/artifacts/results/<name>.jsonl`
- Report: `benchmark/artifacts/reports/<name>.report.json`

**Key options**:
| Option | Default | Description |
|--------|---------|-------------|
| `--dataset` | locbench_v1.jsonl | Dataset path |
| `-o, --output` | auto | Output file prefix |
| `--limit` | all | Number of cases |
| `--seed` | `0` | Random seed |
| `--shuffle` | off | Randomize selection |
| `--max-turns` | env | Override `SEARCH_MAX_TURNS` |
| `--temperature` | env | Override `SEARCH_TEMPERATURE` |
| `--prompt-file` | env | Override `SEARCH_PROMPT_FILE` (YAML) |
| `--timeout` | none | Per-case timeout in seconds |
| `--fail-fast` | none | Stop after N consecutive failures |
| `--resume` | off | Resume from checkpoint |
| `-v, --verbose` | off | Detailed logging |
| `-q, --quiet` | off | Disable progress bar |
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

## 4. Dataset Validation

Validate dataset correctness before running benchmarks:

```bash
# Validate default dataset
uv run python -m benchmark.cli.validate

# Validate specific dataset
uv run python -m benchmark.cli.validate --input artifacts/data/raw/locbench_v1.jsonl

# Output report to file
uv run python -m benchmark.cli.validate --output validation.json --verbose
```

**Validation checks**:
- `hard_gt` / `soft_context` files exist
- Line ranges are valid
- Function names match AST parsing
- `target_ranges` fall within context range
- Solvability evidence appears in query

**Options**:
| Option | Default | Description |
|--------|---------|-------------|
| `--input` | `locbench_v1.jsonl` | Dataset path |
| `--output` | stdout | Report output path |
| `--limit` | all | Number to validate |
| `-v/--verbose` | off | Detailed output |

## 5. Analyze and Report Results

```bash
# Analyze single run (detailed stdout)
uv run python -m benchmark.cli.analyze path/to/run.report.json

# Compare multiple runs (Markdown output)
uv run python -m benchmark.cli.report run1.report.json run2.report.json

# Find best config from grid search
uv run python -m benchmark.cli.report --best grid_curated_30.grid.json

# Output comparison to file
uv run python -m benchmark.cli.report -o comparison.md *.report.json
```

## 6. Interpret Metrics

| Metric | Formula |
|--------|---------|
| File Recall | GT files found / Total GT files |
| File Precision | Correct files / Returned files |
| Line Coverage | GT lines covered / Total GT lines |
| Line Precision | Correct lines / Returned lines |
| Line Prec (Matched) | Correct lines / Returned lines (matched files only) |
| Function Hit Rate | Functions with overlap / Total functions |

Each `*.report.json` includes metadata tracking: `temperature`, `max_turns`, `prompt_file` for reproducibility.

## 7. Troubleshooting

| Problem | Solution |
|---------|----------|
| Missing API key | Set `RELACE_API_KEY` or provider-specific key |
| Clone fails | Check network, ensure `git` installed |
| Dataset not found | Place dataset in `benchmark/artifacts/data/` |
| Slow first run | Normal—repos cached after first download |

## 8. Running Unit Tests

```bash
uv run pytest benchmark/tests -v
```

## Directory Structure

```
benchmark/
├── cli/
│   ├── run.py           # Single run CLI
│   ├── grid.py          # Grid search CLI
│   ├── report.py        # Report generation
│   ├── analyze.py       # Detailed analysis
│   ├── curate.py        # Dataset curation
│   ├── validate.py      # Dataset validation
│   └── build_locbench.py  # Loc-Bench builder
├── analysis/            # Analysis tools (function scope, etc.)
├── datasets/            # Dataset loaders
├── metrics/             # Metrics implementation
├── runner/              # Execution pipeline
├── tests/               # Unit tests
├── config.py            # Configuration constants
├── schemas.py           # Data structure definitions
└── artifacts/           # (runtime generated, not in version control)
    ├── data/            # Dataset files
    ├── repos/           # Cached repositories
    ├── results/         # Run outputs (.jsonl)
    └── reports/         # Summary reports (.report.json, .grid.json)
```
