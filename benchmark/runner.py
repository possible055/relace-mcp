import subprocess  # nosec B404
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from relace_mcp.clients import SearchLLMClient
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.search import FastAgenticSearchHarness

from .metrics import (
    compute_file_precision,
    compute_file_recall,
    compute_line_coverage,
    compute_line_precision,
)
from .swe_bench import BenchmarkCase, get_repos_dir


@dataclass
class BenchmarkResult:
    case_id: str
    repo: str
    success: bool
    file_recall: float
    file_precision: float
    line_coverage: float
    line_precision: float
    turns_used: int
    latency_ms: float
    partial: bool = False
    error: str | None = None


@dataclass
class BenchmarkSummary:
    total_cases: int
    success_rate: float
    avg_file_recall: float
    avg_file_precision: float
    avg_line_coverage: float
    avg_line_precision: float
    avg_turns: float
    avg_latency_ms: float
    results: list[BenchmarkResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "success_rate": self.success_rate,
            "avg_file_recall": self.avg_file_recall,
            "avg_file_precision": self.avg_file_precision,
            "avg_line_coverage": self.avg_line_coverage,
            "avg_line_precision": self.avg_line_precision,
            "avg_turns": self.avg_turns,
            "avg_latency_ms": self.avg_latency_ms,
            "results": [asdict(r) for r in self.results],
        }


class BenchmarkRunner:
    def __init__(self, config: RelaceConfig, *, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.repos_dir = get_repos_dir()
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def run_benchmark(self, cases: list[BenchmarkCase]) -> BenchmarkSummary:
        """Run benchmark on all cases and return summary."""
        results: list[BenchmarkResult] = []

        for i, case in enumerate(cases):
            if self.verbose:
                print(f"[{i + 1}/{len(cases)}] Running {case.id}...")

            result = self._run_case(case)
            results.append(result)

            if self.verbose:
                status = "✓" if result.success else "✗"
                print(
                    f"  {status} Recall={result.file_recall:.2f} "
                    f"Turns={result.turns_used} Latency={result.latency_ms:.0f}ms"
                )

        return self._compute_summary(results)

    def _run_case(self, case: BenchmarkCase) -> BenchmarkResult:
        """Run a single benchmark case."""
        try:
            repo_path = self._ensure_repo(case)
            return self._execute_search(case, repo_path)
        except Exception as e:
            return BenchmarkResult(
                case_id=case.id,
                repo=case.repo,
                success=False,
                file_recall=0.0,
                file_precision=0.0,
                line_coverage=0.0,
                line_precision=0.0,
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
            if self.verbose:
                print(f"  Cloning {case.repo}...")
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

        return BenchmarkResult(
            case_id=case.id,
            repo=case.repo,
            success=not result.get("partial", False),
            file_recall=file_recall,
            file_precision=file_precision,
            line_coverage=line_coverage,
            line_precision=line_precision,
            turns_used=result.get("turns_used", 0),
            latency_ms=latency_ms,
            partial=result.get("partial", False),
        )

    def _compute_summary(self, results: list[BenchmarkResult]) -> BenchmarkSummary:
        """Compute aggregate statistics."""
        n = len(results)
        if n == 0:
            return BenchmarkSummary(
                total_cases=0,
                success_rate=0.0,
                avg_file_recall=0.0,
                avg_file_precision=0.0,
                avg_line_coverage=0.0,
                avg_line_precision=0.0,
                avg_turns=0.0,
                avg_latency_ms=0.0,
                results=[],
            )

        return BenchmarkSummary(
            total_cases=n,
            success_rate=sum(1 for r in results if r.success) / n,
            avg_file_recall=sum(r.file_recall for r in results) / n,
            avg_file_precision=sum(r.file_precision for r in results) / n,
            avg_line_coverage=sum(r.line_coverage for r in results) / n,
            avg_line_precision=sum(r.line_precision for r in results) / n,
            avg_turns=sum(r.turns_used for r in results) / n,
            avg_latency_ms=sum(r.latency_ms for r in results) / n,
            results=results,
        )
