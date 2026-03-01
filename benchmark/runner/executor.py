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

logger = logging.getLogger(__name__)


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
    # ANSI: \033[2K clears the entire line, \r returns cursor to start
    print(f"\033[2K\r{line}", end="", flush=True)


class CaseTimeoutError(Exception):
    pass


_MCP_SETTINGS_KEYS = (
    "LOG_PATH",
    "MCP_LOGGING",
    "MCP_LOG_FILE_LEVEL",
    "MCP_LOG_INCLUDE_KINDS",
    "MCP_LOG_EXCLUDE_KINDS",
    "MAX_LOG_SIZE_BYTES",
    "MCP_TRACE_LOGGING",
)


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

        self._logs_dir: Path | None = None
        self._log_path: Path | None = None
        self._log_offset: int = 0
        self._log_remainder: bytes = b""

    def _configure_mcp_file_logging(self, log_path: Path) -> None:
        import relace_mcp.config.settings as mcp_settings

        # Snapshot current settings for later restoration
        self._mcp_settings_snapshot = {k: getattr(mcp_settings, k) for k in _MCP_SETTINGS_KEYS}

        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            log_path.unlink(missing_ok=True)
        except Exception:
            pass

        mcp_settings.LOG_PATH = log_path
        mcp_settings.MCP_LOGGING = True
        mcp_settings.MCP_LOG_FILE_LEVEL = "DEBUG"
        mcp_settings.MCP_LOG_INCLUDE_KINDS = frozenset()
        mcp_settings.MCP_LOG_EXCLUDE_KINDS = frozenset()
        mcp_settings.MAX_LOG_SIZE_BYTES = 1024 * 1024 * 1024

        # Benchmark trace analysis uses relace.log only; keep the heavy trace log off by default.
        mcp_settings.MCP_TRACE_LOGGING = False

    def _restore_mcp_file_logging(self) -> None:
        if not hasattr(self, "_mcp_settings_snapshot"):
            return
        import relace_mcp.config.settings as mcp_settings

        for k, v in self._mcp_settings_snapshot.items():
            setattr(mcp_settings, k, v)
        del self._mcp_settings_snapshot

    def _read_new_log_events(self) -> list[dict[str, Any]]:
        if self._log_path is None or not self._log_path.exists():
            return []

        try:
            with self._log_path.open("rb") as f:
                f.seek(self._log_offset)
                data = f.read()
                self._log_offset = f.tell()
        except Exception:
            return []

        if not data:
            return []

        buf = self._log_remainder + data
        lines = buf.split(b"\n")
        self._log_remainder = lines.pop() if lines else b""

        events: list[dict[str, Any]] = []
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw.decode("utf-8")))
            except Exception:
                continue
        return events

    def _write_case_trace_from_events(
        self,
        *,
        case_id: str,
        trace_id: str,
        events: list[dict[str, Any]],
        trace_file: Path,
    ) -> str | None:
        # Build per-turn trace objects compatible with benchmark.analysis.trace_analyzer
        turn_map: dict[int, dict[str, Any]] = {}

        for ev in events:
            if ev.get("trace_id") != trace_id:
                continue
            kind = ev.get("kind")
            if kind == "search_turn":
                turn_raw = ev.get("turn")
                try:
                    turn = int(turn_raw)
                except (TypeError, ValueError):
                    continue

                entry = turn_map.get(turn)
                if entry is None:
                    entry = {
                        "turn": turn,
                        "llm_latency_ms": 0.0,
                        "llm_response": {"usage": {}},
                        "tool_results": [],
                        "report_back": None,
                    }
                    turn_map[turn] = entry

                if "llm_latency_ms" in ev:
                    try:
                        entry["llm_latency_ms"] = float(ev["llm_latency_ms"])
                    except (TypeError, ValueError):
                        pass

                usage: dict[str, int] = {}
                if isinstance(ev.get("prompt_tokens"), int):
                    usage["prompt_tokens"] = ev["prompt_tokens"]
                elif isinstance(ev.get("prompt_tokens_est"), int):
                    usage["prompt_tokens"] = ev["prompt_tokens_est"]

                if isinstance(ev.get("completion_tokens"), int):
                    usage["completion_tokens"] = ev["completion_tokens"]

                if isinstance(ev.get("total_tokens"), int):
                    usage["total_tokens"] = ev["total_tokens"]
                else:
                    usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get(
                        "completion_tokens", 0
                    )

                entry["llm_response"] = {"usage": usage}

            elif kind == "tool_call":
                turn_raw = ev.get("turn")
                try:
                    turn = int(turn_raw)
                except (TypeError, ValueError):
                    continue

                entry = turn_map.get(turn)
                if entry is None:
                    entry = {
                        "turn": turn,
                        "llm_latency_ms": 0.0,
                        "llm_response": {"usage": {}},
                        "tool_results": [],
                        "report_back": None,
                    }
                    turn_map[turn] = entry

                tool_name = ev.get("tool_name")
                if not isinstance(tool_name, str):
                    tool_name = "unknown"

                result_preview = ev.get("result_preview")
                if not isinstance(result_preview, str):
                    result_preview = ""

                success = ev.get("success", True)
                if not success and not result_preview.startswith("Error:"):
                    result_preview = "Error: [REDACTED]"

                entry["tool_results"].append(
                    {
                        "name": tool_name,
                        "result": result_preview,
                    }
                )

                if tool_name == "report_back":
                    entry["report_back"] = True

        if not turn_map:
            return None

        total_turns = max(turn_map)
        turns: list[dict[str, Any]] = []
        for t in range(1, total_turns + 1):
            turns.append(
                turn_map.get(
                    t,
                    {
                        "turn": t,
                        "llm_latency_ms": 0.0,
                        "llm_response": {"usage": {}},
                        "tool_results": [],
                        "report_back": None,
                    },
                )
            )

        try:
            with trace_file.open("w", encoding="utf-8") as tf:
                for turn_entry in turns:
                    tf.write(json.dumps(turn_entry, ensure_ascii=False, default=str) + "\n")
            return str(trace_file)
        except Exception:
            return None

    def _write_turns_log(self, turns_log: list[dict[str, Any]], trace_file: Path) -> str | None:
        try:
            with trace_file.open("w", encoding="utf-8") as tf:
                for entry in turns_log:
                    tf.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            return str(trace_file)
        except Exception:
            return None

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

            logs_base = self.repos_dir.parent / "logs"
            self._logs_dir = logs_base / started_at.strftime("%Y%m%d_%H%M%S")
            self._logs_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = self._logs_dir / "relace.log"
            self._log_offset = 0
            self._log_remainder = b""
            self._configure_mcp_file_logging(self._log_path)

        try:
            return self._run_benchmark_loop(cases, started_at=started_at, run_config=run_config)
        finally:
            self._restore_mcp_file_logging()

    def _run_benchmark_loop(
        self,
        cases: list[DatasetCase],
        *,
        started_at: datetime,
        run_config: dict[str, Any] | None = None,
    ) -> BenchmarkSummary:
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
                        # Backward compatibility: map old 'latency_ms' to 'latency_s'
                        if "latency_ms" in data and "latency_s" not in data:
                            data["latency_s"] = data.pop("latency_ms") / 1000.0
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
            from relace_mcp.config.settings import RETRIEVAL_BACKEND
            from relace_mcp.tools.retrieval import agentic_retrieval_logic

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

        # Write trace file if tracing is enabled
        trace_path_str: str | None = None
        if self.trace and self._traces_dir:
            trace_file = self._traces_dir / f"{case.id}.jsonl"
            turns_log = result.get("turns_log")
            if turns_log:
                # Primary: complete data from harness (full LLM response + tool results)
                trace_path_str = self._write_turns_log(turns_log, trace_file)
            else:
                # Fallback: reconstruct from relace.log (truncated previews)
                trace_id = result.get("trace_id") if isinstance(result, dict) else None
                if isinstance(trace_id, str) and trace_id:
                    new_events = self._read_new_log_events()
                    trace_path_str = self._write_case_trace_from_events(
                        case_id=case.id,
                        trace_id=trace_id,
                        events=new_events,
                        trace_file=trace_file,
                    )

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
            hints_used=result.get("cloud_hints_used", 0) if self.search_mode == "indexed" else 0,
            search_mode=self.search_mode,
            retrieval_backend=result.get("retrieval_backend"),
            retrieval_latency_s=result.get("retrieval_latency_s"),
            reindex_action=result.get("reindex_action"),
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
                    "partial_cases": 0,
                    "scored_cases": 0,
                },
                results=[],
            )

        # Exclude partial cases (no report_back) from metric averages to avoid
        # inflating recall/precision with accidentally-observed files.
        scored = [r for r in results if not r.partial]
        ns = len(scored)

        def avg(field: str) -> float:
            if ns == 0:
                return 0.0
            return sum(getattr(r, field) for r in scored) / ns

        # Compute quality_score: weighted combination of recall + precision + function hit
        # Weights: file_recall=0.3, file_precision=0.2, line_precision_matched=0.3, function_hit_rate=0.2
        def quality_score(r: BenchmarkResult) -> float:
            func_weight = 0.2 if r.functions_total > 0 else 0.0
            remaining = 1.0 - func_weight
            return (
                (remaining * 3 / 8) * r.file_recall
                + (remaining * 2 / 8) * r.file_precision
                + (remaining * 3 / 8) * r.line_precision_matched
                + func_weight * r.function_hit_rate
            )

        avg_quality_score = (sum(quality_score(r) for r in scored) / ns) if ns else 0.0

        function_results = [r for r in scored if r.functions_total > 0]
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
            "partial_cases": n - ns,
            "scored_cases": ns,
        }

        return BenchmarkSummary(
            metadata=metadata,
            total_cases=n,
            stats=stats,
            results=results,
        )
