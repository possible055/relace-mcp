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
from relace_mcp.search import FastAgenticSearchHarness

from ..analysis.metrics import (
    compute_file_precision,
    compute_file_recall,
    compute_function_hits,
    compute_line_coverage,
    compute_line_precision_matched,
    normalize_returned_files,
)
from ..analysis.traces import ArtifactStatus
from ..config.paths import get_experiments_dir, get_repos_dir
from ..schemas import DatasetCase
from .git import ensure_repo
from .layout import results_path
from .metadata import build_experiment_manifest, build_initial_state
from .models import BenchmarkResult, BenchmarkSummary
from .trace_recorder import BenchmarkTraceRecorder

logger = logging.getLogger(__name__)


REQUIRED_RESULT_FIELDS = {
    "case_id",
    "repo",
    "completed",
    "returned_files_count",
    "ground_truth_files_count",
    "file_recall",
    "file_precision",
    "line_coverage",
    "line_precision_matched",
    "context_line_coverage",
    "context_line_precision_matched",
    "function_hit_rate",
    "functions_hit",
    "functions_total",
    "turns_used",
    "latency_s",
}


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
    scored = [r for r in results if not r.partial]
    n = len(scored)
    if n == 0:
        return f"({len(results)} partial)"
    avg_recall = sum(r.file_recall for r in scored) / n
    avg_precision = sum(r.file_precision for r in scored) / n
    partial_count = len(results) - n
    suffix = f" +{partial_count}p" if partial_count else ""
    return f"R:{avg_recall:.0%} P:{avg_precision:.0%}{suffix}"


def _print_progress(line: str) -> None:
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
        artifact_root: Path | None = None,
    ):
        self.config = config
        self.verbose = verbose
        self.progress = progress
        self.repos_dir = get_repos_dir()
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_checkpoint_path = checkpoint_path
        self.case_timeout = case_timeout
        self.fail_fast = fail_fast
        self.search_mode = search_mode
        self.resume = resume
        self.trace = trace
        self.artifact_root = artifact_root
        self.trace_recorder: BenchmarkTraceRecorder | None = None

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
        experiment_root = self.artifact_root or (
            get_experiments_dir() / started_at.strftime("%Y%m%d_%H%M%S")
        )
        experiment_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = experiment_root

        run_id = experiment_root.name
        self.trace_recorder = BenchmarkTraceRecorder(
            enabled=self.trace,
            experiment_root=experiment_root,
            run_id=run_id,
            search_mode=self.search_mode,
        )
        self.trace_recorder.start_run()

        try:
            return self._run_benchmark_loop(cases, started_at=started_at, run_config=run_config)
        finally:
            self.trace_recorder.finish_run()

    def _load_existing_results(self, path: Path) -> tuple[set[str], list[BenchmarkResult]]:
        completed_ids: set[str] = set()
        loaded: list[BenchmarkResult] = []
        if not path.exists():
            return completed_ids, loaded

        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Unsupported result schema: invalid JSON (path={path}, line={lineno}): {exc}"
                    ) from exc
                if not isinstance(data, dict):
                    raise RuntimeError(
                        f"Unsupported result schema: expected JSON object (path={path}, line={lineno})"
                    )
                if not REQUIRED_RESULT_FIELDS.issubset(data.keys()):
                    missing = sorted(REQUIRED_RESULT_FIELDS - set(data.keys()))
                    raise RuntimeError(
                        f"Unsupported result schema (path={path}, line={lineno}): missing fields {missing}."
                    )
                result = BenchmarkResult.from_dict(data)
                completed_ids.add(result.case_id)
                loaded.append(result)
        return completed_ids, loaded

    def _run_benchmark_loop(
        self,
        cases: list[DatasetCase],
        *,
        started_at: datetime,
        run_config: dict[str, Any] | None = None,
    ) -> BenchmarkSummary:
        wall_start = time.perf_counter()
        total = len(cases)
        consecutive_failures = 0
        interrupted = False
        results_file_path = results_path(self.artifact_root)
        results_file_path.parent.mkdir(parents=True, exist_ok=True)

        completed_ids: set[str] = set()
        results: list[BenchmarkResult] = []
        if self.resume:
            completed_ids, results = self._load_existing_results(results_file_path)
            if completed_ids:
                print(f"Resumed {len(completed_ids)} completed cases from {results_file_path}")

        results_file = results_file_path.open("a", encoding="utf-8")
        try:
            for i, case in enumerate(cases):
                current = i + 1

                if case.id in completed_ids:
                    if self.progress and not self.verbose:
                        progress_bar = _format_progress_bar(current, total)
                        _print_progress(f"{progress_bar} [{current}/{total}] {case.id} (cached)")
                    continue

                elapsed = time.perf_counter() - wall_start
                eta = _format_eta(elapsed, len(results), total)
                stats = _format_running_stats(results)
                if self.progress and not self.verbose:
                    progress_bar = _format_progress_bar(current - 1, total)
                    _print_progress(f"{progress_bar} [{current}/{total}] {case.id} {eta} {stats}")

                if self.verbose:
                    print(f"[{current}/{total}] {case.id} ({case.repo})", flush=True)

                result = self._run_case_with_timeout(case)
                results.append(result)
                results_file.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
                results_file.flush()

                if result.completed:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                if self.verbose:
                    status_icon = "✓" if result.completed else "✗"
                    print(
                        f"  {status_icon} recall={result.file_recall:.0%} search={result.latency_s:.1f}s",
                        flush=True,
                    )

                if self.fail_fast and consecutive_failures >= self.fail_fast:
                    interrupted = True
                    print(f"\nFail-fast triggered: {consecutive_failures} consecutive failures")
                    break
        finally:
            results_file.close()

        if self.progress and not self.verbose:
            progress_bar = _format_progress_bar(total if not interrupted else len(results), total)
            print(f"\033[2K\r{progress_bar} done {_format_running_stats(results)}", flush=True)

        completed_at = datetime.now(UTC)
        kind = "run"
        if isinstance(run_config, dict):
            kind = str(run_config.get("experiment_type", "run") or "run")
        manifest = build_experiment_manifest(
            config=self.config,
            experiment_id=self.artifact_root.name,
            kind=kind,
            experiment_root=self.artifact_root,
            cases=cases,
            run_config={**(run_config or {}), "repos_dir": str(self.repos_dir)},
            created_at=started_at,
            artifacts=(self.trace_recorder.artifact_metadata() if self.trace_recorder else {}),
        )
        state = build_initial_state(total)
        state.completed_cases = sum(1 for result in results if result.completed)
        state.failed_cases = len(results) - state.completed_cases
        state.status = "failed" if interrupted else "completed"
        state.updated_at = completed_at

        return self._compute_summary(results, manifest=manifest, state=state)

    def _run_case_with_timeout(self, case: DatasetCase) -> BenchmarkResult:
        if self.case_timeout is None:
            return self._run_case(case)

        def timeout_handler(_signum: int, _frame: types.FrameType | None) -> None:
            raise CaseTimeoutError(f"Case timed out after {self.case_timeout}s")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.case_timeout)
        try:
            return self._run_case(case)
        except CaseTimeoutError as exc:
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
                error=str(exc),
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
        except Exception as exc:
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
                error=str(exc),
            )

    def _execute_search(self, case: DatasetCase, repo_path: Path) -> BenchmarkResult:
        effective_config = replace(self.config, base_dir=str(repo_path))
        client = SearchLLMClient(effective_config)

        if self.trace_recorder is not None:
            self.trace_recorder.write_search_start(
                case_id=case.id, repo=case.repo, query=case.query
            )

        start_time = time.perf_counter()
        lsp_languages = get_lsp_languages(repo_path)
        if self.search_mode == "indexed":
            import asyncio

            from relace_mcp.clients import RelaceRepoClient
            from relace_mcp.config.settings import RETRIEVAL_BACKEND
            from relace_mcp.search import agentic_retrieval_logic

            from .preflight import check_retrieval_backend

            preflight = check_retrieval_backend(RETRIEVAL_BACKEND or "auto", str(repo_path))
            logger.info("Retrieval preflight: %s", preflight)

            repo_client = RelaceRepoClient(effective_config)
            result = asyncio.run(
                agentic_retrieval_logic(
                    repo_client,
                    client,
                    effective_config,
                    str(repo_path),
                    case.query,
                    trace=self.trace,
                )
            )
        else:
            result = FastAgenticSearchHarness(
                effective_config,
                client,
                lsp_languages=lsp_languages,
                trace=self.trace,
            ).run(case.query)

        latency_s = round(time.perf_counter() - start_time, 1)
        trace_path_str: str | None = None
        trace_meta_path_str: str | None = None
        turns_log: list[dict[str, Any]] | None = None
        artifact_status: ArtifactStatus = (
            {"trace_jsonl": "disabled", "trace_meta": "disabled"}
            if not self.trace
            else {"trace_jsonl": "missing", "trace_meta": "missing"}
        )
        raw_turns_log = result.get("turns_log")
        if isinstance(raw_turns_log, list):
            turns_log = raw_turns_log

        if self.trace_recorder is not None:
            trace_write = self.trace_recorder.write_case_trace(case_id=case.id, turns_log=turns_log)
            trace_path_str = trace_write.path
            artifact_status["trace_jsonl"] = trace_write.state
            if trace_write.warnings:
                warnings = [
                    warning for warning in result.get("warnings", []) if isinstance(warning, str)
                ]
                warnings.extend(trace_write.warnings)
                result["warnings"] = warnings

            meta_write = self.trace_recorder.write_case_meta(
                case_id=case.id,
                repo=case.repo,
                query=case.query,
                result=result,
            )
            trace_meta_path_str = meta_write.path
            artifact_status["trace_meta"] = meta_write.state
            if meta_write.warnings:
                warnings = [
                    warning for warning in result.get("warnings", []) if isinstance(warning, str)
                ]
                warnings.extend(meta_write.warnings)
                result["warnings"] = warnings

        returned_files_raw = result.get("files", {})
        if not isinstance(returned_files_raw, dict):
            returned_files_raw = {}
        returned_files = normalize_returned_files(returned_files_raw, repo_root=repo_path)

        ground_truth_files = case.ground_truth_files
        context_ground_truth_files = case.ground_truth_context_files
        function_targets = [
            (target["path"], target["ranges"]) for target in case.ground_truth_functions
        ]
        functions_hit, functions_total = compute_function_hits(
            returned_files,
            function_targets,
            repo_root=repo_path,
        )

        benchmark_result = BenchmarkResult(
            case_id=case.id,
            repo=case.repo,
            completed=not bool(result.get("partial", False)),
            returned_files_count=len(returned_files),
            ground_truth_files_count=len(ground_truth_files),
            file_recall=compute_file_recall(
                returned_files, ground_truth_files, repo_root=repo_path
            ),
            file_precision=compute_file_precision(
                returned_files, ground_truth_files, repo_root=repo_path
            ),
            line_coverage=compute_line_coverage(
                returned_files, ground_truth_files, repo_root=repo_path
            ),
            line_precision_matched=compute_line_precision_matched(
                returned_files,
                ground_truth_files,
                repo_root=repo_path,
            ),
            context_line_coverage=compute_line_coverage(
                returned_files,
                context_ground_truth_files,
                repo_root=repo_path,
            ),
            context_line_precision_matched=compute_line_precision_matched(
                returned_files,
                context_ground_truth_files,
                repo_root=repo_path,
            ),
            function_hit_rate=(functions_hit / functions_total) if functions_total else 0.0,
            functions_hit=functions_hit,
            functions_total=functions_total,
            turns_used=int(result.get("turns_used", 0) or 0),
            latency_s=latency_s,
            partial=bool(result.get("partial", False)),
            error=result.get("error") if isinstance(result.get("error"), str) else None,
            returned_files=returned_files,
            trace_path=trace_path_str,
            trace_meta_path=trace_meta_path_str,
            artifact_status=artifact_status,
            hints_used=result.get("semantic_hints_used", 0) if self.search_mode == "indexed" else 0,
            search_mode=self.search_mode,
            retrieval_backend=result.get("retrieval_backend"),
            retrieval_latency_s=result.get("retrieval_latency_s"),
            reindex_action=result.get("reindex_action"),
        )

        if self.trace_recorder is not None:
            self.trace_recorder.write_case_events(
                case_id=case.id,
                repo=case.repo,
                benchmark_result=benchmark_result,
                result=result,
                turns_log=turns_log,
            )

        return benchmark_result

    def _compute_summary(
        self,
        results: list[BenchmarkResult],
        *,
        manifest,
        state,
    ) -> BenchmarkSummary:
        n = len(results)
        if n == 0:
            return BenchmarkSummary(
                manifest=manifest,
                state=state,
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
                    "partial_cases": 0,
                    "scored_cases": 0,
                },
                results=[],
            )

        scored = [result for result in results if not result.partial]
        ns = len(scored)

        def avg(field: str) -> float:
            if ns == 0:
                return 0.0
            return sum(getattr(result, field) for result in scored) / ns

        def quality_score(result: BenchmarkResult) -> float:
            func_weight = 0.2 if result.functions_total > 0 else 0.0
            remaining = 1.0 - func_weight
            return (
                (remaining * 3 / 8) * result.file_recall
                + (remaining * 2 / 8) * result.file_precision
                + (remaining * 3 / 8) * result.line_precision_matched
                + func_weight * result.function_hit_rate
            )

        avg_quality_score = (sum(quality_score(result) for result in scored) / ns) if ns else 0.0
        function_results = [result for result in scored if result.functions_total > 0]
        function_cases = len(function_results)
        avg_function_hit_rate = (
            sum(result.function_hit_rate for result in function_results) / function_cases
            if function_cases
            else 0.0
        )

        return BenchmarkSummary(
            manifest=manifest,
            state=state,
            stats={
                "completion_rate": sum(1 for result in results if result.completed) / n,
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
                "partial_cases": n - ns,
                "scored_cases": ns,
            },
            results=results,
        )
