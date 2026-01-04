# Benchmark Module for fast_search Evaluation
#
# Sub-modules:
#   cli/        - CLI entry points (run, filter, validate, analyze)
#   datasets/   - Dataset loaders (MULocBench, filtered)
#   metrics/    - Metric implementations
#   analysis/   - AST and code analysis (tree-sitter)
#   filters/    - LLM-based evaluators (solvability, relevance)
#   runner/     - Execution pipeline
#
# Usage:
#   from benchmark.datasets.mulocbench import load_mulocbench, BenchmarkCase
#   from benchmark.metrics import compute_file_recall, compute_line_coverage
#   from benchmark.runner.executor import BenchmarkRunner
#   from benchmark.runner.results import BenchmarkResult, BenchmarkSummary
