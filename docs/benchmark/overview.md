# Benchmark

Evaluate the code localization accuracy of `agentic_search` and `agentic_retrieval` using the [Loc-Bench](https://github.com/gersteinlab/LocAgent) dataset — a curated collection of real-world code search tasks across open-source repositories.

!!! warning "Under Development"
    APIs and metric definitions may change.

## Overview

The benchmark measures how well the search tools can **locate relevant code** given a natural-language query. Each test case specifies:

- A **query** describing what to find (e.g., "where is authentication handled")
- A **ground truth** — the exact files, line ranges, and functions that should be returned
- A **repository** pinned to a specific commit for reproducibility

The evaluation produces file-level, line-level, and function-level metrics that quantify both **recall** (did we find what matters?) and **precision** (did we avoid returning noise?).

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Python | 3.12+ (managed by `uv`) |
| Git | Required for cloning evaluation repos |
| API Key | `RELACE_API_KEY` or provider-specific key in `.env` |
| Disk Space | ~2 GB for cached repos under `artifacts/repos/` |

Create a `.env` file in the project root:

```bash
SEARCH_PROVIDER=relace    # Options: relace, openai, openrouter
RELACE_API_KEY=<key>      # API key for your provider
```

## Quick Start

```bash
# 1. Build the dataset
uv run python -m benchmark.cli.build_locbench \
  --output artifacts/data/raw/locbench_v1.jsonl

# 2. Run evaluation
uv run python -m benchmark.cli.run \
  --dataset artifacts/data/raw/locbench_v1.jsonl \
  --limit 50

# 3. Analyze results
uv run python -m benchmark.cli.analyze artifacts/reports/<name>.report.json
```

## Workflow

A typical benchmarking session follows three stages:

### 1. Build Dataset

Convert the upstream Loc-Bench data into the internal JSONL format:

```bash
uv run python -m benchmark.cli.build_locbench \
  --output artifacts/data/raw/locbench_v1.jsonl
```

Optionally validate the dataset to check ground truth integrity:

```bash
uv run python -m benchmark.cli.validate --input artifacts/data/raw/locbench_v1.jsonl
```

This verifies file existence, line range validity, function name AST matching, and `target_ranges` containment within context ranges.

### 2. Run Evaluation

Run a single evaluation pass:

```bash
uv run python -m benchmark.cli.run \
  --dataset artifacts/data/raw/locbench_v1.jsonl \
  --limit 50 --shuffle
```

Or sweep across hyperparameters with grid search:

```bash
uv run python -m benchmark.cli.grid \
  --dataset artifacts/data/processed/elite_50.jsonl \
  --limit 50 --shuffle \
  --max-turns 4 --max-turns 6 --max-turns 8 \
  --temperatures 0 --temperatures 0.2 --temperatures 0.4
```

Each run produces two output files:

| File | Content |
|------|---------|
| `artifacts/results/<name>.jsonl` | Per-case detailed results |
| `artifacts/reports/<name>.report.json` | Aggregated summary report |

### 3. Analyze Results

```bash
# Single run — detailed breakdown
uv run python -m benchmark.cli.analyze path/to/run.report.json

# Compare multiple runs side-by-side
uv run python -m benchmark.cli.report run1.report.json run2.report.json

# Find best configuration from a grid search
uv run python -m benchmark.cli.report --best grid.grid.json
```

## CLI Reference

### `run` — Single Evaluation

```bash
uv run python -m benchmark.cli.run [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dataset PATH` | Dataset JSONL path |
| `-o, --output PREFIX` | Output file prefix (default: auto-generated with timestamp) |
| `--limit N` | Maximum number of cases to evaluate |
| `--shuffle` | Randomly sample cases |
| `--seed N` | Random seed (default: `0`) |
| `--max-turns N` | Override `SEARCH_MAX_TURNS` |
| `--temperature F` | Override `SEARCH_TEMPERATURE` |
| `--search-mode MODE` | `agentic` (default) or `indexed` |
| `--lsp-tools MODE` | LSP tools: `true`, `false`, or `auto` |
| `--enabled-tools LIST` | Comma-separated list of enabled tools |
| `--prompt-file PATH` | Override `SEARCH_PROMPT_FILE` (YAML) |
| `--timeout N` | Per-case timeout in seconds |
| `--fail-fast N` | Stop after N consecutive failures |
| `--resume` | Resume from checkpoint |
| `--dry-run` | Load data only, skip execution |
| `-v, --verbose` | Verbose output |
| `-q, --quiet` | Disable progress bar |

### `grid` — Hyperparameter Grid Search

Runs the Cartesian product of `max_turns × temperature`:

```bash
uv run python -m benchmark.cli.grid [OPTIONS]
```

Accepts the same options as `run`, plus:

| Option | Description |
|--------|-------------|
| `--max-turns N` | One or more turn counts (repeatable) |
| `--temperatures F` | One or more temperature values (repeatable) |

**Output**: `artifacts/reports/<grid_name>.grid.json`

### `validate` — Dataset Validation

```bash
uv run python -m benchmark.cli.validate --input <dataset.jsonl>
```

Checks:

- Ground truth file existence in the target repo
- Line range validity
- Function name matches via AST parsing
- `target_ranges` within context range bounds

### `analyze` / `report` — Results Analysis

```bash
uv run python -m benchmark.cli.analyze <report.json>
uv run python -m benchmark.cli.report <run1.json> <run2.json> [...]
uv run python -m benchmark.cli.report --best <grid.json>
```

## Metrics

### File-Level Metrics

**File Recall** — What fraction of the ground truth files were found?

$$\text{File Recall} = \frac{|\text{returned files} \cap \text{GT files}|}{|\text{GT files}|}$$

A recall of **1.0** means every relevant file was included in the results.

**File Precision** — What fraction of returned files were actually relevant?

$$\text{File Precision} = \frac{|\text{returned files} \cap \text{GT files}|}{|\text{returned files}|}$$

A precision of **1.0** means no irrelevant files were returned.

### Line-Level Metrics

**Line Coverage** — How many ground truth lines were covered by the returned ranges?

$$\text{Line Coverage} = \frac{|\text{returned lines} \cap \text{GT lines}|}{|\text{GT lines}|}$$

**Line Precision (Matched)** — Among files that matched, how accurate were the returned line ranges?

$$\text{Line Precision}_M = \frac{|\text{correct lines in matched files}|}{|\text{returned lines in matched files}|}$$

This metric is restricted to **matched files only** to avoid penalizing file-level misses twice.

### Function-Level Metrics

**Function Hit Rate** — How many ground truth functions had overlapping coverage?

$$\text{Function Hit Rate} = \frac{\text{functions with overlap}}{\text{total GT functions}}$$

A function is considered "hit" if any returned line range overlaps with its definition.

### Quality Score

A single composite metric for quick comparison:

$$\text{Quality Score} = 0.4 \times \text{File Recall} + 0.4 \times \text{Line Precision}_M + 0.2 \times \text{Function Hit Rate}$$

## Interpreting Results

After running a benchmark, the `.report.json` file contains aggregated statistics. Here is an example summary:

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

**How to read this:**

- **File Recall 0.72** — The search found 72% of the files it should have. Room for improvement, but most relevant files are surfaced.
- **Line Precision (M) 0.71** — When the right file is found, 71% of the returned lines are actually relevant. Higher is better; values below 0.5 suggest overly broad ranges.
- **Quality Score 0.67** — The composite metric. Compare this across runs to gauge overall improvement.
- **Latency 3200 ms** — Average wall-clock time per case. Useful for spotting timeout issues.
- **Turns 4.2** — Average agentic search iterations. More turns generally improve recall at the cost of latency.

### What "Good" Looks Like

These are rough reference points — actual targets depend on your use case:

| Metric | Baseline | Good | Excellent |
|--------|----------|------|-----------|
| File Recall | 0.50 | 0.70 | 0.85+ |
| File Precision | 0.40 | 0.60 | 0.75+ |
| Line Coverage | 0.30 | 0.55 | 0.70+ |
| Line Precision (M) | 0.40 | 0.65 | 0.80+ |
| Function Hit Rate | 0.35 | 0.60 | 0.75+ |
| Quality Score | 0.40 | 0.65 | 0.80+ |

!!! tip
    Use `--max-turns` and `--temperature` to trade off between latency and accuracy. Higher turns typically improve recall; lower temperature improves precision.

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| API key error | Missing or invalid key in `.env` | Verify `RELACE_API_KEY` or provider-specific key |
| Clone failed | Network issue or missing `git` | Check connectivity; ensure `git` is installed |
| Slow first run | Repos being cloned for the first time | Normal — repos are cached to `artifacts/repos/` on subsequent runs |
| Out of memory | Too many cases loaded | Use `--limit` to reduce the number of cases |
| Timeout errors | Cases exceeding per-case limit | Increase `--timeout` or check API responsiveness |
| Inconsistent results | Non-deterministic LLM output | Set `--temperature 0` and fix `--seed` for reproducibility |
| Resume not working | Missing checkpoint file | Ensure the previous run wrote to the same output path |

## Running Tests

```bash
uv run pytest benchmark/tests -v
```
