import asyncio
import logging
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.lsp.languages import get_lsp_languages
from relace_mcp.tools.search import DualChannelHarness, FastAgenticSearchHarness

from ..analysis.ast_spans import normalize_to_ast_spans
from ..analysis.call_graph import expand_ground_truth
from ..config import get_repos_dir
from ..metrics import (
    compute_file_precision,
    compute_file_recall,
    compute_function_hits,
    compute_line_coverage,
    compute_line_precision_matched,
)
from ..schemas import DatasetCase
from .git import ensure_repo
from .metadata import build_run_metadata
from .results import BenchmarkResult, BenchmarkSummary


def _format_progress_bar(current: int, total: int, width: int = 30) -> str:
    """Format a simple ASCII progress bar."""
    if total == 0:
        return "[" + " " * width + "]"
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = current * 100 // total
    return f"[{bar}] {pct:3d}%"


class BenchmarkRunner:
    def __init__(
        self,
        config: RelaceConfig,
        *,
        verbose: bool = False,
        progress: bool = True,
        beta: float = 0.5,
        normalize_ast: bool = False,
        soft_gt: bool = False,
        harness_type: Literal["fast", "dual"] = "dual",
    ):
        self.config = config
        self.verbose = verbose
        self.progress = progress
        self.beta = beta
        self.normalize_ast = normalize_ast
        self.soft_gt = soft_gt
        self.harness_type = harness_type
        self.repos_dir = get_repos_dir()
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def run_benchmark(
        self,
        cases: list[DatasetCase],
        *,
        run_config: dict[str, Any] | None = None,
    ) -> BenchmarkSummary:
        """Run benchmark on all cases and return summary."""
        # Suppress logger warnings during progress mode to avoid interfering with progress bar
        relace_logger = logging.getLogger("relace_mcp")
        original_level = relace_logger.level
        if self.progress and not self.verbose:
            relace_logger.setLevel(logging.ERROR)

        try:
            return self._run_benchmark_inner(cases, run_config=run_config)
        finally:
            relace_logger.setLevel(original_level)

    def _run_benchmark_inner(
        self,
        cases: list[DatasetCase],
        *,
        run_config: dict[str, Any] | None = None,
    ) -> BenchmarkSummary:
        """Internal benchmark loop."""
        started_at = datetime.now(UTC)
        wall_start = time.perf_counter()
        results: list[BenchmarkResult] = []
        total = len(cases)
        last_line_len = 0

        for i, case in enumerate(cases):
            current = i + 1

            if self.progress and not self.verbose:
                progress_bar = _format_progress_bar(current - 1, total)
                line = f"{progress_bar} [{current}/{total}] {case.id}"
                padding = " " * max(0, last_line_len - len(line))
                print(f"\r{line}{padding}", end="", flush=True)
                last_line_len = len(line)

            if self.verbose:
                print(f"[{current}/{total}] {case.id} ({case.repo})", flush=True)

            result = self._run_case(case)
            results.append(result)

            if self.verbose:
                status_icon = "✓" if result.success else "✗"
                print(
                    f"  {status_icon} recall={result.file_recall:.0%} "
                    f"search={result.latency_ms / 1000:.1f}s",
                    flush=True,
                )

        if self.progress and not self.verbose:
            progress_bar = _format_progress_bar(total, total)
            line = f"{progress_bar} done"
            padding = " " * max(0, last_line_len - len(line))
            print(f"\r{line}{padding}", flush=True)

        completed_at = datetime.now(UTC)
        duration_ms = (time.perf_counter() - wall_start) * 1000
        metadata = build_run_metadata(
            config=self.config,
            repos_dir=self.repos_dir,
            cases=cases,
            run_config=run_config,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
        return self._compute_summary(results, metadata=metadata)

    def _run_case(self, case: DatasetCase) -> BenchmarkResult:
        try:
            repo_path = ensure_repo(
                repos_dir=self.repos_dir,
                repo=case.repo,
                base_commit=case.base_commit,
                verbose=(self.verbose or self.progress),
            )

            return self._execute_search(case, repo_path)
        except Exception as e:
            return BenchmarkResult(
                case_id=case.id,
                repo=case.repo,
                success=False,
                returned_files_count=0,
                ground_truth_files_count=len(case.ground_truth_files),
                file_recall=0.0,
                file_precision=0.0,
                line_coverage=0.0,
                line_precision_matched=0.0,
                function_hit_rate=0.0,
                functions_hit=0,
                functions_total=len(case.ground_truth_functions),
                turns_used=0,
                latency_ms=0.0,
                partial=True,
                error=str(e),
            )

    def _execute_search(self, case: DatasetCase, repo_path: Path) -> BenchmarkResult:
        effective_config = replace(self.config, base_dir=str(repo_path))
        client = SearchLLMClient(effective_config)

        start_time = time.perf_counter()
        lsp_languages = get_lsp_languages(repo_path)
        if self.harness_type == "dual":
            result = asyncio.run(
                DualChannelHarness(effective_config, client, lsp_languages=lsp_languages).run_async(
                    case.query
                )
            )
        else:
            result = FastAgenticSearchHarness(
                effective_config, client, lsp_languages=lsp_languages
            ).run(case.query)
        latency_ms = (time.perf_counter() - start_time) * 1000

        returned_files = result.get("files", {})
        if not isinstance(returned_files, dict):
            returned_files = {}

        returned_files_count = len(returned_files)

        # Optionally normalize ground truth to AST boundaries
        if self.normalize_ast:
            ground_truth_files = self._normalize_ground_truth(case, repo_path)
        else:
            ground_truth_files = case.ground_truth_files

        # Optionally expand ground truth with called functions
        if self.soft_gt:
            soft_ranges = expand_ground_truth(repo_path, ground_truth_files)
            ground_truth_files = self._merge_soft_gt(ground_truth_files, soft_ranges)

        ground_truth_files_count = len(ground_truth_files)

        file_recall = compute_file_recall(
            returned_files,
            ground_truth_files,
            repo_root=repo_path,
        )
        file_precision = compute_file_precision(
            returned_files,
            ground_truth_files,
            repo_root=repo_path,
        )

        line_coverage = compute_line_coverage(
            returned_files,
            ground_truth_files,
            repo_root=repo_path,
        )
        line_precision_matched = compute_line_precision_matched(
            returned_files,
            ground_truth_files,
            repo_root=repo_path,
        )

        function_targets = [(t["path"], t["ranges"]) for t in case.ground_truth_functions]
        functions_hit, functions_total = compute_function_hits(
            returned_files,
            function_targets,
            repo_root=repo_path,
        )
        function_hit_rate = (functions_hit / functions_total) if functions_total else 0.0

        error = result.get("error") if isinstance(result.get("error"), str) else None
        partial = bool(result.get("partial", False))

        return BenchmarkResult(
            case_id=case.id,
            repo=case.repo,
            success=not partial,
            returned_files_count=returned_files_count,
            ground_truth_files_count=ground_truth_files_count,
            file_recall=file_recall,
            file_precision=file_precision,
            line_coverage=line_coverage,
            line_precision_matched=line_precision_matched,
            function_hit_rate=function_hit_rate,
            functions_hit=functions_hit,
            functions_total=functions_total,
            turns_used=int(result.get("turns_used", 0) or 0),
            latency_ms=latency_ms,
            partial=partial,
            error=error,
        )

    def _normalize_ground_truth(
        self, case: DatasetCase, repo_path: Path
    ) -> dict[str, list[tuple[int, int]]]:
        """Normalize ground truth line ranges to AST node boundaries."""
        normalized: dict[str, list[tuple[int, int]]] = {}
        gt_files = case.ground_truth_files

        for file_path, ranges in gt_files.items():
            if not ranges:
                continue

            full_path = repo_path / file_path
            if not full_path.exists() or not file_path.endswith(".py"):
                # Not a Python file or doesn't exist, use original ranges
                normalized[file_path] = ranges
                continue

            # Extract all lines from ranges for AST normalization
            raw_lines: set[int] = set()
            for start, end in ranges:
                raw_lines.update(range(start, end + 1))

            ast_ranges = normalize_to_ast_spans(full_path, raw_lines, context_padding=2)
            if ast_ranges:
                normalized[file_path] = ast_ranges
            else:
                normalized[file_path] = ranges

        return normalized

    def _merge_soft_gt(
        self,
        original: dict[str, list[tuple[int, int]]],
        soft: dict[str, list[tuple[int, int]]],
    ) -> dict[str, list[tuple[int, int]]]:
        """Merge soft ground truth ranges into original ground truth."""
        merged = dict(original)
        for file_path, ranges in soft.items():
            if file_path in merged:
                merged[file_path] = merged[file_path] + ranges
            else:
                merged[file_path] = ranges
        return merged

    def _compute_summary(
        self,
        results: list[BenchmarkResult],
        *,
        metadata: dict[str, Any],
    ) -> BenchmarkSummary:
        n = len(results)
        if n == 0:
            return BenchmarkSummary(
                metadata=metadata,
                total_cases=0,
                stats={
                    "success_rate": 0.0,
                    "avg_returned_files": 0.0,
                    "avg_ground_truth_files": 0.0,
                    "avg_file_recall": 0.0,
                    "avg_file_precision": 0.0,
                    "avg_line_coverage": 0.0,
                    "avg_line_precision_matched": 0.0,
                    "function_cases": 0,
                    "avg_function_hit_rate": 0.0,
                    "avg_turns": 0.0,
                    "avg_latency_ms": 0.0,
                },
                results=[],
            )

        def avg(field: str) -> float:
            return sum(getattr(r, field) for r in results) / n

        function_results = [r for r in results if r.functions_total > 0]
        function_cases = len(function_results)
        avg_function_hit_rate = (
            (sum(r.function_hit_rate for r in function_results) / function_cases)
            if function_cases
            else 0.0
        )

        stats: dict[str, float] = {
            "success_rate": sum(1 for r in results if r.success) / n,
            "avg_returned_files": avg("returned_files_count"),
            "avg_ground_truth_files": avg("ground_truth_files_count"),
            "avg_file_recall": avg("file_recall"),
            "avg_file_precision": avg("file_precision"),
            "avg_line_coverage": avg("line_coverage"),
            "avg_line_precision_matched": avg("line_precision_matched"),
            "function_cases": function_cases,
            "avg_function_hit_rate": avg_function_hit_rate,
            "avg_turns": avg("turns_used"),
            "avg_latency_ms": avg("latency_ms"),
        }

        return BenchmarkSummary(
            metadata=metadata,
            total_cases=n,
            stats=stats,
            results=results,
        )
