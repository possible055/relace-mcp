import platform
import subprocess  # nosec B404
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.config import settings as relace_settings
from relace_mcp.config.settings import RELACE_PROVIDER
from relace_mcp.tools.search import FastAgenticSearchHarness
from relace_mcp.tools.search.schemas.tool_schemas import get_tool_schemas

from .metrics import (
    compute_file_precision,
    compute_file_recall,
    compute_function_hits,
    compute_line_coverage,
    compute_line_iou_matched,
    compute_line_precision,
    compute_line_precision_matched,
)
from .mulocbench import BenchmarkCase, get_repos_dir


def _format_progress_bar(current: int, total: int, width: int = 30) -> str:
    """Format a simple ASCII progress bar."""
    if total == 0:
        return "[" + " " * width + "]"
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = current * 100 // total
    return f"[{bar}] {pct:3d}%"


def _sanitize_endpoint_url(url: str) -> str:
    """Sanitize endpoint URL for logs/metadata (strip credentials, query, fragments)."""
    try:
        parts = urlsplit(url)
    except Exception:
        return url

    if not parts.scheme or not parts.netloc:
        return url

    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if not host:
        host = parts.netloc.split("@")[-1]

    netloc = host
    if parts.port is not None:
        netloc = f"{host}:{parts.port}"

    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


@dataclass
class BenchmarkResult:
    case_id: str
    repo: str
    success: bool
    returned_files_count: int
    ground_truth_files_count: int
    file_recall: float
    file_precision: float
    file_f1: float
    line_coverage: float
    line_precision: float
    line_precision_matched: float
    line_iou_matched: float
    function_hit_rate: float
    functions_hit: int
    functions_total: int
    turns_used: int
    latency_ms: float
    repo_prep_ms: float = 0.0
    repo_cached: bool = False
    partial: bool = False
    error: str | None = None


@dataclass
class BenchmarkSummary:
    metadata: dict[str, Any]
    total_cases: int
    success_rate: float
    avg_returned_files: float
    avg_ground_truth_files: float
    avg_file_recall: float
    avg_file_precision: float
    avg_file_f1: float
    avg_line_coverage: float
    avg_line_precision: float
    avg_line_precision_matched: float
    avg_line_iou_matched: float
    function_cases: int
    avg_function_hit_rate: float
    avg_turns: float
    avg_latency_ms: float
    avg_repo_prep_ms: float
    results: list[BenchmarkResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "total_cases": self.total_cases,
            "success_rate": self.success_rate,
            "avg_returned_files": self.avg_returned_files,
            "avg_ground_truth_files": self.avg_ground_truth_files,
            "avg_file_recall": self.avg_file_recall,
            "avg_file_precision": self.avg_file_precision,
            "avg_file_f1": self.avg_file_f1,
            "avg_line_coverage": self.avg_line_coverage,
            "avg_line_precision": self.avg_line_precision,
            "avg_line_precision_matched": self.avg_line_precision_matched,
            "avg_line_iou_matched": self.avg_line_iou_matched,
            "function_cases": self.function_cases,
            "avg_function_hit_rate": self.avg_function_hit_rate,
            "avg_turns": self.avg_turns,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_repo_prep_ms": self.avg_repo_prep_ms,
            "results": [asdict(r) for r in self.results],
        }


class BenchmarkRunner:
    def __init__(self, config: RelaceConfig, *, verbose: bool = False, progress: bool = True):
        self.config = config
        self.verbose = verbose
        self.progress = progress
        self.repos_dir = get_repos_dir()
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def _git_has_commit(self, repo_path: Path, commit: str) -> bool:
        completed = subprocess.run(  # nosec B603 B607
            ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=False,
            capture_output=True,
        )
        return completed.returncode == 0

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
                progress_bar = _format_progress_bar(current - 1, total)
                line = f"{progress_bar} [{current}/{total}] {case.id}"
                # Pad with spaces to clear previous longer line
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

        # Print final progress and newline
        if self.progress and not self.verbose:
            progress_bar = _format_progress_bar(total, total)
            line = f"{progress_bar} done"
            padding = " " * max(0, last_line_len - len(line))
            print(f"\r{line}{padding}", flush=True)

        completed_at = datetime.now(UTC)
        duration_ms = (time.perf_counter() - wall_start) * 1000
        metadata = self._build_run_metadata(
            cases,
            run_config=run_config,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
        return self._compute_summary(results, metadata=metadata)

    def _run_case(self, case: BenchmarkCase) -> BenchmarkResult:
        """Run a single benchmark case."""
        try:
            repo_name = case.repo.replace("/", "__")
            expected_repo_path = self.repos_dir / repo_name
            repo_cached = expected_repo_path.exists()

            prep_start = time.perf_counter()
            repo_path = self._ensure_repo(case)
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

    def _ensure_repo(self, case: BenchmarkCase) -> Path:
        """Clone and checkout repo if needed."""
        repo_name = case.repo.replace("/", "__")
        repo_path = self.repos_dir / repo_name

        if not repo_path.exists():
            if self.verbose or self.progress:
                print(f"  Cloning {case.repo}...", flush=True)
            subprocess.run(  # nosec B603 B607
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    f"https://github.com/{case.repo}.git",
                    str(repo_path),
                ],
                check=True,
                capture_output=True,
            )

        # Fetch the specific commit and checkout
        if not self._git_has_commit(repo_path, case.base_commit):
            subprocess.run(  # nosec B603 B607
                ["git", "-C", str(repo_path), "fetch", "--depth", "1", "origin", case.base_commit],
                check=True,
                capture_output=True,
            )
        subprocess.run(  # nosec B603 B607
            ["git", "-C", str(repo_path), "checkout", case.base_commit],
            check=True,
            capture_output=True,
        )

        return repo_path

    def _execute_search(self, case: BenchmarkCase, repo_path: Path) -> BenchmarkResult:
        """Execute fast_search and compute metrics."""
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

        return BenchmarkResult(
            case_id=case.id,
            repo=case.repo,
            success=not result.get("partial", False),
            returned_files_count=returned_files_count,
            ground_truth_files_count=ground_truth_files_count,
            file_recall=file_recall,
            file_precision=file_precision,
            file_f1=file_f1,
            line_coverage=line_coverage,
            line_precision=line_precision,
            line_precision_matched=line_precision_matched,
            line_iou_matched=line_iou_matched,
            function_hit_rate=function_hit_rate,
            functions_hit=functions_hit,
            functions_total=functions_total,
            turns_used=result.get("turns_used", 0),
            latency_ms=latency_ms,
            partial=result.get("partial", False),
        )

    def _compute_summary(
        self,
        results: list[BenchmarkResult],
        *,
        metadata: dict[str, Any],
    ) -> BenchmarkSummary:
        """Compute aggregate statistics."""
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
            avg_line_precision_matched=sum(r.line_precision_matched for r in results) / n,
            avg_line_iou_matched=sum(r.line_iou_matched for r in results) / n,
            function_cases=function_cases,
            avg_function_hit_rate=avg_function_hit_rate,
            avg_turns=sum(r.turns_used for r in results) / n,
            avg_latency_ms=sum(r.latency_ms for r in results) / n,
            avg_repo_prep_ms=sum(r.repo_prep_ms for r in results) / n,
            results=results,
        )

    def _build_run_metadata(
        self,
        cases: list[BenchmarkCase],
        *,
        run_config: dict[str, Any] | None,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: float,
    ) -> dict[str, Any]:
        """Build reproducibility metadata for this benchmark run (no secrets)."""
        # NOTE: Intentionally avoid recording any API keys.
        config_meta: dict[str, Any] = {
            "base_dir": self.config.base_dir,
            "default_encoding": self.config.default_encoding,
        }

        search_client = SearchLLMClient(self.config)
        provider_config = search_client._provider_config

        # Match BenchmarkRunner's harness default: lsp_languages=None -> empty frozenset.
        tool_schemas = get_tool_schemas(frozenset())
        tool_names: list[str] = []
        tool_has_strict = False
        for schema in tool_schemas:
            func = schema.get("function")
            if not isinstance(func, dict):
                continue
            name = func.get("name")
            if isinstance(name, str) and name:
                tool_names.append(name)
            if "strict" in func:
                tool_has_strict = True
        tool_names = sorted(set(tool_names + ["report_back"]))

        # SearchLLMClient currently hard-codes these request params.
        request_params: dict[str, Any] = {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 100 if provider_config.api_compat == RELACE_PROVIDER else None,
            "repetition_penalty": (1.0 if provider_config.api_compat == RELACE_PROVIDER else None),
        }

        case_list = [
            {
                "id": c.id,
                "repo": c.repo,
                "base_commit": c.base_commit,
                "issue_url": c.issue_url,
                "pr_url": c.pr_url,
            }
            for c in cases
        ]

        relace_mcp_commit: str | None = None
        try:
            project_root = Path(__file__).resolve().parent.parent
            completed = subprocess.run(  # nosec B603 B607
                ["git", "-C", str(project_root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            relace_mcp_commit = completed.stdout.strip() or None
        except Exception:
            relace_mcp_commit = None

        relace_mcp_version: str | None = None
        try:
            relace_mcp_version = importlib_metadata.version("relace-mcp")
        except importlib_metadata.PackageNotFoundError:
            relace_mcp_version = None

        run_meta = dict(run_config) if isinstance(run_config, dict) else {}
        run_meta.setdefault("cases_loaded", len(cases))

        return {
            "run": {
                **run_meta,
                "started_at_utc": started_at.isoformat(),
                "completed_at_utc": completed_at.isoformat(),
                "duration_ms": round(duration_ms, 2),
            },
            "config": config_meta,
            "dataset": {
                "repos_dir": str(self.repos_dir),
                "cases": case_list,
            },
            "search": {
                "provider": provider_config.provider,
                "api_compat": provider_config.api_compat,
                "base_url": _sanitize_endpoint_url(provider_config.base_url),
                "model": provider_config.model,
                "timeout_seconds": relace_settings.SEARCH_TIMEOUT_SECONDS,
                "max_turns": relace_settings.SEARCH_MAX_TURNS,
                "tools": tool_names,
                "tool_strict": tool_has_strict,
                **request_params,
            },
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "relace_mcp_version": relace_mcp_version,
                "relace_mcp_git_commit": relace_mcp_commit,
            },
        }
