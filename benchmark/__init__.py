# Benchmark Module for agentic_search Evaluation
#
# Sub-modules:
#   cli/        - CLI entry points (run, filter, validate, analyze)
#   datasets/   - Dataset loaders (MULocBench, filtered)
#   metrics/    - Metric implementations
#   analysis/   - AST and code analysis (tree-sitter)
#   config/     - Paths and settings
#   runner/     - Execution pipeline
#
# Usage:
#   from benchmark.datasets import load_dataset, DatasetCase
#   from benchmark.metrics import compute_file_recall, compute_line_coverage
#   from benchmark.runner.executor import BenchmarkRunner
#   from benchmark.runner.results import BenchmarkResult, BenchmarkSummary
