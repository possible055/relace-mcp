import json
import logging
import signal
import time
import types
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.lsp.languages import get_lsp_languages
from relace_mcp.tools.search import FastAgenticSearchHarness

from ..config import get_repos_dir
from ..metrics import (
    compute_file_precision,
    compute_file_recall,
    compute_function_hits,
    compute_line_coverage,
    compute_line_precision_matched,
)
from ..metrics.paths import normalize_returned_files
from ..schemas import DatasetCase
from .git import ensure_repo
from .metadata import build_run_metadata
from .results import BenchmarkResult, BenchmarkSummary


def _format_progress_bar(current: int, total: int, width: int = 30) -> str:
    if total == 0:
        return "[" + " " * width + "]"
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = current * 100 // total
    return f"[{bar}] {pct:3d}%"


def _format_eta(elapsed_seconds: float, current: int, total: int) -> str:
    if current == 0:
        return "ETA: --:--"
    avg_per_case = elapsed_seconds / current
    remaining = (total - current) * avg_per_case
    mins, secs = divmod(int(remaining), 60)
    return f"ETA: {mins:02d}:{secs:02d}"


def _format_running_stats(results: list[BenchmarkResult]) -> str:
    if not results:
        return ""
    n = len(results)
    avg_recall = sum(r.file_recall for r in results) / n
    avg_precision = sum(r.file_precision for r in results) / n
    return f"R:{avg_recall:.0%} P:{avg_precision:.0%}"


def _print_progress(line: str) -> None:
    # ANSI: \033[2K clears the entire line, \r returns cursor to start
    print(f"\033[2K\r{line}", end="", flush=True)


class CaseTimeoutError(Exception):
    pass


class BenchmarkRunner:
    def __init__(
        self,
        config: RelaceConfig,
        *,
        verbose: bool = False,
        progress: bool = True,
        checkpoint_path: Path | None = None,
        case_timeout: int | None = None,
        fail_fast: int | None = None,
        search_mode: str = "agentic",
        resume: bool = False,
        trace: bool = False,
    ):
        self.config = config
        self.verbose = verbose
        self.progress = progress
        self.repos_dir = get_repos_dir()
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = checkpoint_path
        self.case_timeout = case_timeout
        self.fail_fast = fail_fast
        self.search_mode = search_mode
        self.resume = resume
        self.trace = trace
        self._traces_dir: Path | None = None

    def run_benchmark(
        self,
        cases: list[DatasetCase],
        *,
        run_config: dict[str, Any] | None = None,
    ) -> BenchmarkSummary:
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
        started_at = datetime.now(UTC)

        if self.trace:
            traces_base = self.repos_dir.parent / "traces"
            self._traces_dir = traces_base / started_at.strftime("%Y%m%d_%H%M%S")
            self._traces_dir.mkdir(parents=True, exist_ok=True)

        wall_start = time.perf_counter()
        results: list[BenchmarkResult] = []
        total = len(cases)
        consecutive_failures = 0

        # Resume: load completed cases from checkpoint
        completed_ids: set[str] = set()
        if self.resume and self.checkpoint_path and self.checkpoint_path.exists():
            with self.checkpoint_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        # Backward compatibility: map old 'success' field to 'completed'
                        if "success" in data and "completed" not in data:
                            data["completed"] = data.pop("success")
                        completed_ids.add(data["case_id"])
                        results.append(
                            BenchmarkResult(
                                **{
                                    k: v
                                    for k, v in data.items()
                                    if k in BenchmarkResult.__dataclass_fields__
                                }
                            )
                        )
                    except (json.JSONDecodeError, KeyError):
                        continue
            if completed_ids:
                print(f"Resumed {len(completed_ids)} completed cases from checkpoint")

        # Open checkpoint file for appending new results
        checkpoint_file = None
        if self.checkpoint_path:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_file = self.checkpoint_path.open("a", encoding="utf-8")

        try:
            for i, case in enumerate(cases):
                current = i + 1

                # Skip already completed cases
                if case.id in completed_ids:
                    if self.progress and not self.verbose:
                        progress_bar = _format_progress_bar(current, total)
                        line = f"{progress_bar} [{current}/{total}] {case.id} (cached)"
                        _print_progress(line)
                    continue

                elapsed = time.perf_counter() - wall_start
                eta = _format_eta(elapsed, len(results), total)
                stats = _format_running_stats(results)

                if self.progress and not self.verbose:
                    progress_bar = _format_progress_bar(current - 1, total)
                    line = f"{progress_bar} [{current}/{total}] {case.id} {eta} {stats}"
                    _print_progress(line)

                if self.verbose:
                    print(f"[{current}/{total}] {case.id} ({case.repo})", flush=True)

                result = self._run_case_with_timeout(case)
                results.append(result)

                # Write to checkpoint immediately
                if checkpoint_file:
                    from dataclasses import asdict

                    checkpoint_file.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
                    checkpoint_file.flush()

                # Track consecutive failures for fail-fast
                if result.completed:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                if self.verbose:
                    status_icon = "✓" if result.completed else "✗"
                    print(
                        f"  {status_icon} recall={result.file_recall:.0%} "
                        f"search={result.latency_s:.1f}s",
                        flush=True,
                    )

                # Fail-fast check
                if self.fail_fast and consecutive_failures >= self.fail_fast:
                    print(f"\nFail-fast triggered: {consecutive_failures} consecutive failures")
                    break

        finally:
            if checkpoint_file:
                checkpoint_file.close()

        if self.progress and not self.verbose:
            progress_bar = _format_progress_bar(total, total)
            final_stats = _format_running_stats(results)
            line = f"{progress_bar} done {final_stats}"
            print(f"\033[2K\r{line}", flush=True)

        completed_at = datetime.now(UTC)
        duration_s = time.perf_counter() - wall_start
        metadata = build_run_metadata(
            config=self.config,
            repos_dir=self.repos_dir,
            cases=cases,
            run_config=run_config,
            started_at=started_at,
            completed_at=completed_at,
            duration_s=duration_s,
        )
        return self._compute_summary(results, metadata=metadata)

    def _run_case_with_timeout(self, case: DatasetCase) -> BenchmarkResult:
        if self.case_timeout is None:
            return self._run_case(case)

        def timeout_handler(_signum: int, _frame: types.FrameType | None) -> None:
            raise CaseTimeoutError(f"Case timed out after {self.case_timeout}s")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.case_timeout)
        try:
            return self._run_case(case)
        except CaseTimeoutError as e:
            return BenchmarkResult(
                case_id=case.id,
                repo=case.repo,
                completed=False,
                returned_files_count=0,
                ground_truth_files_count=len(case.ground_truth_files),
                file_recall=0.0,
                file_precision=0.0,
                line_coverage=0.0,
                line_precision_matched=0.0,
                context_line_coverage=0.0,
                context_line_precision_matched=0.0,
                function_hit_rate=0.0,
                functions_hit=0,
                functions_total=len(case.ground_truth_functions),
                turns_used=0,
                latency_s=float(self.case_timeout),
                partial=True,
                error=str(e),
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

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
                completed=False,
                returned_files_count=0,
                ground_truth_files_count=len(case.ground_truth_files),
                file_recall=0.0,
                file_precision=0.0,
                line_coverage=0.0,
                line_precision_matched=0.0,
                context_line_coverage=0.0,
                context_line_precision_matched=0.0,
                function_hit_rate=0.0,
                functions_hit=0,
                functions_total=len(case.ground_truth_functions),
                turns_used=0,
                latency_s=0.0,
                partial=True,
                error=str(e),
            )

    def _execute_search(self, case: DatasetCase, repo_path: Path) -> BenchmarkResult:
        effective_config = replace(self.config, base_dir=str(repo_path))
        client = SearchLLMClient(effective_config)

        start_time = time.perf_counter()
        lsp_languages = get_lsp_languages(repo_path)

        if self.search_mode == "indexed":
            import asyncio

            from relace_mcp.clients import RelaceRepoClient
            from relace_mcp.tools.retrieval import agentic_retrieval_logic

            repo_client = RelaceRepoClient(effective_config)
            result = asyncio.run(
                agentic_retrieval_logic(
                    repo_client,
                    client,
                    effective_config,
                    str(repo_path),
                    case.query,
                )
            )
        else:
            result = FastAgenticSearchHarness(
                effective_config, client, lsp_languages=lsp_languages, trace=self.trace
            ).run(case.query)

        latency_s = round(time.perf_counter() - start_time, 1)

        # Write trace file if tracing is enabled
        trace_path_str: str | None = None
        if self.trace and self._traces_dir and "turns_log" in result:
            trace_file = self._traces_dir / f"{case.id}.jsonl"
            try:
                with trace_file.open("w", encoding="utf-8") as tf:
                    for turn_entry in result["turns_log"]:
                        tf.write(json.dumps(turn_entry, ensure_ascii=False, default=str) + "\n")
                trace_path_str = str(trace_file)
            except Exception:
                pass

        returned_files_raw = result.get("files", {})
        if not isinstance(returned_files_raw, dict):
            returned_files_raw = {}

        returned_files = normalize_returned_files(returned_files_raw, repo_root=repo_path)
        returned_files_count = len(returned_files)

        context_ground_truth_files = case.ground_truth_context_files
        ground_truth_files = case.ground_truth_files
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

        context_line_coverage = compute_line_coverage(
            returned_files,
            context_ground_truth_files,
            repo_root=repo_path,
        )
        context_line_precision_matched = compute_line_precision_matched(
            returned_files,
            context_ground_truth_files,
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
            completed=not partial,
            returned_files_count=returned_files_count,
            ground_truth_files_count=ground_truth_files_count,
            file_recall=file_recall,
            file_precision=file_precision,
            line_coverage=line_coverage,
            line_precision_matched=line_precision_matched,
            context_line_coverage=context_line_coverage,
            context_line_precision_matched=context_line_precision_matched,
            function_hit_rate=function_hit_rate,
            functions_hit=functions_hit,
            functions_total=functions_total,
            turns_used=int(result.get("turns_used", 0) or 0),
            latency_s=latency_s,
            partial=partial,
            error=error,
            returned_files=returned_files,
            raw_result=result,
            trace_path=trace_path_str,
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
                stats={
                    "completion_rate": 0.0,
                    "avg_quality_score": 0.0,
                    "avg_returned_files": 0.0,
                    "avg_ground_truth_files": 0.0,
                    "avg_file_recall": 0.0,
                    "avg_file_precision": 0.0,
                    "avg_line_coverage": 0.0,
                    "avg_line_precision_matched": 0.0,
                    "avg_context_line_coverage": 0.0,
                    "avg_context_line_precision_matched": 0.0,
                    "function_cases": 0,
                    "avg_function_hit_rate": 0.0,
                    "avg_turns": 0.0,
                    "avg_latency_s": 0.0,
                },
                results=[],
            )

        def avg(field: str) -> float:
            return sum(getattr(r, field) for r in results) / n

        # Compute quality_score: weighted combination of recall + precision + function hit
        # Weights: file_recall=0.4, line_precision_matched=0.4, function_hit_rate=0.2
        def quality_score(r: BenchmarkResult) -> float:
            func_weight = 0.2 if r.functions_total > 0 else 0.0
            remaining = 1.0 - func_weight
            return (
                (remaining / 2) * r.file_recall
                + (remaining / 2) * r.line_precision_matched
                + func_weight * r.function_hit_rate
            )

        avg_quality_score = sum(quality_score(r) for r in results) / n

        function_results = [r for r in results if r.functions_total > 0]
        function_cases = len(function_results)
        avg_function_hit_rate = (
            (sum(r.function_hit_rate for r in function_results) / function_cases)
            if function_cases
            else 0.0
        )

        stats: dict[str, float] = {
            "completion_rate": sum(1 for r in results if r.completed) / n,
            "avg_quality_score": avg_quality_score,
            "avg_returned_files": avg("returned_files_count"),
            "avg_ground_truth_files": avg("ground_truth_files_count"),
            "avg_file_recall": avg("file_recall"),
            "avg_file_precision": avg("file_precision"),
            "avg_line_coverage": avg("line_coverage"),
            "avg_line_precision_matched": avg("line_precision_matched"),
            "avg_context_line_coverage": avg("context_line_coverage"),
            "avg_context_line_precision_matched": avg("context_line_precision_matched"),
            "function_cases": function_cases,
            "avg_function_hit_rate": avg_function_hit_rate,
            "avg_turns": avg("turns_used"),
            "avg_latency_s": avg("latency_s"),
        }

        return BenchmarkSummary(
            metadata=metadata,
            total_cases=n,
            stats=stats,
            results=results,
        )
