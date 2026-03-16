# Benchmark Module

> **Note**: This module is under active development. APIs and metrics may change.

Evaluates `agentic_search` performance using the Loc-Bench dataset (derived from [LocAgent](https://github.com/IvanaXu/LocAgent)).

## 1. Setup

**Prerequisites**: Python 3.11+, `git`, network access

**Execution model**: `benchmark/` is repo-local tooling. Run commands from the repository root with `uv run --extra benchmark ...`. For benchmark tests, also include `--extra dev`.

**Environment** (create `.env` in project root):
```bash
SEARCH_PROVIDER=relace          # or: openai, openrouter
RELACE_API_KEY=your-key-here    # or: OPENAI_API_KEY, OPENROUTER_API_KEY
```

**Dataset**:

Build the Loc-Bench dataset from Hugging Face via datasets-server (no LocAgent required):
```bash
uv run --extra benchmark python -m benchmark.cli.build_locbench \
  --output artifacts/data/raw/locbench_v1.jsonl
```

Create a processed subset for repeatable runs:
```bash
uv run --extra benchmark python -m benchmark.cli.curate --count 50
```

If you use `--local-parquet`, install `pyarrow` in the environment first.

## 2. Single Run

```bash
# Basic run on a curated subset
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/processed/curated_50.jsonl --limit 20

# Run on Loc-Bench (after build_locbench)
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/raw/locbench_v1.jsonl --limit 20

# With parameter overrides
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/processed/curated_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --max-turns 8 --temperature 0.2 -q

# Resume from checkpoint after interruption
uv run --extra benchmark python -m benchmark.cli.run \
  -o my_run --resume --timeout 300 --fail-fast 5
```

**Outputs**:
- Experiment root: `benchmark/artifacts/experiments/<experiment_name>/`
- Results: `benchmark/artifacts/experiments/<experiment_name>/results/results.jsonl`
- Report: `benchmark/artifacts/experiments/<experiment_name>/reports/summary.report.json`
- Traces (when `--trace`): `benchmark/artifacts/experiments/<experiment_name>/traces/<case_id>.jsonl`
- Trace metadata (when `--trace`): `benchmark/artifacts/experiments/<experiment_name>/traces/<case_id>.meta.json`
- Events (when `--trace`): `benchmark/artifacts/experiments/<experiment_name>/events/events.jsonl`

Run reports also include `metadata.artifacts` with the trace `schema_version`, `experiment_root`, `traces_dir`, and `events_path`.

**Trace workflow**:
```bash
# Collect raw traces plus indexed retrieval hint metadata
uv run --extra benchmark python -m benchmark.cli.run \
  --dataset artifacts/data/processed/curated_50.jsonl \
  --limit 10 --trace --search-mode indexed

# Export the derived search map as JSON
uv run --extra benchmark python -m benchmark.cli.trace \
  --latest --search-map --json-out -o search_map.json

# Validate trace/meta/events consistency for the latest run
uv run --extra benchmark python -m benchmark.cli.trace \
  --latest --validate
```

Each run now archives all outputs under one experiment directory. `<case_id>.meta.json` stores retrieval-side metadata for the case, including `semantic_hints` file lists from external index backends. Both trace metadata and run-level events include a `schema_version` field so consumers can validate artifact compatibility.

**Key options**:
| Option | Default | Description |
|--------|---------|-------------|
| `--dataset` | locbench_v1.jsonl | Dataset path |
| `-o, --output` | auto | Experiment directory name/path |
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
| `--trace` | off | Save per-case trace JSONL and run-level events JSONL |

**Search modes**:
- `agentic` is the default and works without retrieval indexing.
- `indexed` requires a usable retrieval backend plus a fresh local index or cloud sync state for each repo.

## 3. Grid Search (Hyperparameter Tuning)

Run Cartesian product of `turns × temperature` combinations:

```bash
uv run --extra benchmark python -m benchmark.cli.grid \
  --dataset artifacts/data/processed/curated_50.jsonl \
  --limit 64 --seed 0 --shuffle \
  --max-turns 4 --max-turns 6 --max-turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4 --temperatures 0.6
```

**Grid options**:
| Option | Required | Description |
|--------|----------|-------------|
| `--max-turns` | ✓ | Grid values for `SEARCH_MAX_TURNS` (repeatable) |
| `--temperatures` | ✓ | Grid values for `SEARCH_TEMPERATURE` (repeatable) |
| `--prompt-file` | | Override `SEARCH_PROMPT_FILE` for all runs |
| `--output` | | Grid experiment directory |
| `--dry-run` | | Print planned runs without executing |

**Output**: Grid summary saved to `artifacts/experiments/<grid_name>/reports/grid.report.json`

## 4. Dataset Validation

Validate dataset correctness before running benchmarks:

```bash
# Validate default dataset
uv run --extra benchmark python -m benchmark.cli.validate

# Validate specific dataset
uv run --extra benchmark python -m benchmark.cli.validate --input artifacts/data/raw/locbench_v1.jsonl

# Output report to file
uv run --extra benchmark python -m benchmark.cli.validate --output validation.json --verbose
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
uv run --extra benchmark python -m benchmark.cli.analyze path/to/run.report.json

# Compare multiple runs from report files (Markdown output)
uv run --extra benchmark python -m benchmark.cli.report run1.report.json run2.report.json

# Find best config from grid search
uv run --extra benchmark python -m benchmark.cli.report --best grid_curated_30.grid.json

# Analyze incomplete / failed cases from a result file
uv run --extra benchmark python -m benchmark.cli.report --failures path/to/run.jsonl

# Output comparison to file
uv run --extra benchmark python -m benchmark.cli.report -o comparison.md *.report.json
```

**Accepted inputs by mode**:
- Comparison mode: one or more `*.report.json`
- `--best`: exactly one `*.grid.json`
- `--failures`: exactly one `*.jsonl`

## 6. Interpret Metrics

| Metric | Formula |
|--------|---------|
| File Recall | GT files found / Total GT files |
| File Precision | Correct files / Returned files |
| Line Coverage | GT lines covered / Total GT lines |
| Line Prec (Matched) | Correct lines / Returned lines (matched files only) |
| Function Hit Rate | Functions with overlap / Total functions |

Each `*.report.json` includes metadata tracking: `temperature`, `max_turns`, `prompt_file` for reproducibility.

## 7. Troubleshooting

| Problem | Solution |
|---------|----------|
| Missing benchmark deps | Run commands with `uv run --extra benchmark ...` |
| Missing API key | Set `RELACE_API_KEY` or provider-specific key |
| Clone fails | Check network, ensure `git` installed |
| `indexed` preflight fails | Ensure the retrieval backend is available and its index / cloud sync state is fresh |
| Dataset not found | Place dataset in `benchmark/artifacts/data/` |
| Slow first run | Normal—repos cached after first download |

## 8. Running Unit Tests

```bash
uv run --extra dev --extra benchmark pytest benchmark/tests -v
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
    ├── experiments/     # Per-experiment archives
    │   └── <experiment_name>/
    │       ├── events/  # Run-level events (.jsonl)
    │       ├── reports/ # Summary reports (.report.json, .grid.json)
    │       ├── results/ # Run outputs (.jsonl)
    │       └── traces/  # Per-case traces (.jsonl + .meta.json)
    ├── repos/           # Cached repositories
```
