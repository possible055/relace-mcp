# Benchmark Module for fast_search Evaluation
#
# Sub-modules:
#   datasets/   - Dataset loaders (MULocBench)
#   evaluation/ - Metric implementations
#   run/        - Execution pipeline
#
# Usage:
#   from benchmark.datasets.mulocbench import load_mulocbench, BenchmarkCase
#   from benchmark.evaluation.metrics import compute_file_recall, ...
#   from benchmark.run.runner import BenchmarkRunner
#   from benchmark.run.models import BenchmarkResult, BenchmarkSummary
