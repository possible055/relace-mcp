import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.search import FastAgenticSearchHarness

from ..datasets.mulocbench import BenchmarkCase
from ..evaluation.metrics import (
    compute_file_precision,
    compute_file_recall,
    compute_function_hits,
    compute_line_coverage,
    compute_line_iou_matched,
    compute_line_precision,
    compute_line_precision_matched,
)
from ..paths import get_repos_dir
from .git import ensure_repo
from .metadata import build_run_metadata
from .models import BenchmarkResult, BenchmarkSummary
from .progress import format_progress_bar


class BenchmarkRunner:
    def __init__(self, config: RelaceConfig, *, verbose: bool = False, progress: bool = True):
        self.config = config
        self.verbose = verbose
        self.progress = progress
        self.repos_dir = get_repos_dir()
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def run_benchmark(
        self,
        cases: list[BenchmarkCase],
        *,
        run_config: dict[str, Any] | None = None,
    ) -> BenchmarkSummary:
        """Run benchmark on all cases and return summary."""
        started_at = datetime.now(UTC)
        wall_start = time.perf_counter()
        results: list[BenchmarkResult] = []
        total = len(cases)
        last_line_len = 0

        for i, case in enumerate(cases):
            current = i + 1

            if self.progress and not self.verbose:
                progress_bar = format_progress_bar(current - 1, total)
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
                    f"prep={result.repo_prep_ms / 1000:.1f}s "
                    f"search={result.latency_ms / 1000:.1f}s",
                    flush=True,
                )

        if self.progress and not self.verbose:
            progress_bar = format_progress_bar(total, total)
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

    def _run_case(self, case: BenchmarkCase) -> BenchmarkResult:
        try:
            repo_name = case.repo.replace("/", "__")
            expected_repo_path = self.repos_dir / repo_name
            repo_cached = expected_repo_path.exists()

            prep_start = time.perf_counter()
            repo_path = ensure_repo(
                repos_dir=self.repos_dir,
                repo=case.repo,
                base_commit=case.base_commit,
                verbose=(self.verbose or self.progress),
            )
            repo_prep_ms = (time.perf_counter() - prep_start) * 1000

            result = self._execute_search(case, repo_path)
            result.repo_prep_ms = repo_prep_ms
            result.repo_cached = repo_cached
            return result
        except Exception as e:
            return BenchmarkResult(
                case_id=case.id,
                repo=case.repo,
                success=False,
                returned_files_count=0,
                ground_truth_files_count=len(case.ground_truth_files),
                file_recall=0.0,
                file_precision=0.0,
                file_f1=0.0,
                line_coverage=0.0,
                line_precision=0.0,
                line_f1=0.0,
                line_precision_matched=0.0,
                line_iou_matched=0.0,
                function_hit_rate=0.0,
                functions_hit=0,
                functions_total=len(case.ground_truth_functions),
                turns_used=0,
                latency_ms=0.0,
                partial=True,
                error=str(e),
            )

    def _execute_search(self, case: BenchmarkCase, repo_path: Path) -> BenchmarkResult:
        effective_config = replace(self.config, base_dir=str(repo_path))
        client = SearchLLMClient(effective_config)
        harness = FastAgenticSearchHarness(effective_config, client)

        start_time = time.perf_counter()
        result = harness.run(case.query)
        latency_ms = (time.perf_counter() - start_time) * 1000

        returned_files = result.get("files", {})
        if not isinstance(returned_files, dict):
            returned_files = {}

        returned_files_count = len(returned_files)
        ground_truth_files_count = len(case.ground_truth_files)

        file_recall = compute_file_recall(
            returned_files,
            case.ground_truth_files,
            repo_root=repo_path,
        )
        file_precision = compute_file_precision(
            returned_files,
            case.ground_truth_files,
            repo_root=repo_path,
        )
        denom = file_recall + file_precision
        file_f1 = (2 * file_recall * file_precision / denom) if denom else 0.0

        line_coverage = compute_line_coverage(
            returned_files,
            case.ground_truth_files,
            repo_root=repo_path,
        )
        line_precision = compute_line_precision(
            returned_files,
            case.ground_truth_files,
            repo_root=repo_path,
        )
        line_denom = line_coverage + line_precision
        line_f1 = (2 * line_coverage * line_precision / line_denom) if line_denom else 0.0
        line_precision_matched = compute_line_precision_matched(
            returned_files,
            case.ground_truth_files,
            repo_root=repo_path,
        )
        line_iou_matched = compute_line_iou_matched(
            returned_files,
            case.ground_truth_files,
            repo_root=repo_path,
        )

        function_targets = [(t.path, t.ranges) for t in case.ground_truth_functions]
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
            file_f1=file_f1,
            line_coverage=line_coverage,
            line_precision=line_precision,
            line_f1=line_f1,
            line_precision_matched=line_precision_matched,
            line_iou_matched=line_iou_matched,
            function_hit_rate=function_hit_rate,
            functions_hit=functions_hit,
            functions_total=functions_total,
            turns_used=int(result.get("turns_used", 0) or 0),
            latency_ms=latency_ms,
            partial=partial,
            error=error,
        )

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
                success_rate=0.0,
                avg_returned_files=0.0,
                avg_ground_truth_files=0.0,
                avg_file_recall=0.0,
                avg_file_precision=0.0,
                avg_file_f1=0.0,
                avg_line_coverage=0.0,
                avg_line_precision=0.0,
                avg_line_f1=0.0,
                avg_line_precision_matched=0.0,
                avg_line_iou_matched=0.0,
                function_cases=0,
                avg_function_hit_rate=0.0,
                avg_turns=0.0,
                avg_latency_ms=0.0,
                avg_repo_prep_ms=0.0,
                results=[],
            )

        function_results = [r for r in results if r.functions_total > 0]
        function_cases = len(function_results)
        avg_function_hit_rate = (
            (sum(r.function_hit_rate for r in function_results) / function_cases)
            if function_cases
            else 0.0
        )

        return BenchmarkSummary(
            metadata=metadata,
            total_cases=n,
            success_rate=sum(1 for r in results if r.success) / n,
            avg_returned_files=sum(r.returned_files_count for r in results) / n,
            avg_ground_truth_files=sum(r.ground_truth_files_count for r in results) / n,
            avg_file_recall=sum(r.file_recall for r in results) / n,
            avg_file_precision=sum(r.file_precision for r in results) / n,
            avg_file_f1=sum(r.file_f1 for r in results) / n,
            avg_line_coverage=sum(r.line_coverage for r in results) / n,
            avg_line_precision=sum(r.line_precision for r in results) / n,
            avg_line_f1=sum(r.line_f1 for r in results) / n,
            avg_line_precision_matched=sum(r.line_precision_matched for r in results) / n,
            avg_line_iou_matched=sum(r.line_iou_matched for r in results) / n,
            function_cases=function_cases,
            avg_function_hit_rate=avg_function_hit_rate,
            avg_turns=sum(r.turns_used for r in results) / n,
            avg_latency_ms=sum(r.latency_ms for r in results) / n,
            avg_repo_prep_ms=sum(r.repo_prep_ms for r in results) / n,
            results=results,
        )
