"""Dataset filtering pipeline with solvability and context evaluation.

This module provides a CLI to filter MULocBench dataset by:
1. Solvability - Ensure problem text is clear enough to locate code
2. Function Scope - Normalize line ranges to complete functions
3. Soft Context - Build call graph context with LLM relevance filtering
"""

import json
import sys
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv

from relace_mcp.config import RelaceConfig

from ..analysis.function_scope import normalize_gt_to_function_scopes
from ..config import EXCLUDED_REPOS, get_benchmark_dir, get_repos_dir
from ..datasets.filtered import FilteredCase, load_filtered_dataset
from ..datasets.mulocbench import BenchmarkCase, load_mulocbench
from ..filters.relevance import ContextRelevanceEvaluator
from ..filters.solvability import SolvabilityEvaluator, SolvabilityResult
from ..runner.git import ensure_repo

# Internal constants
_SOLVABILITY_THRESHOLD = 0.7
_RELEVANCE_THRESHOLD = 0.5


@click.command()
@click.option(
    "--input",
    "input_path",
    default="data/mulocbench.jsonl",
    show_default=True,
    help="Input dataset path (relative to benchmark/)",
)
@click.option(
    "--output",
    "output_path",
    default="data/filtered.jsonl",
    show_default=True,
    help="Output filtered dataset path (relative to benchmark/)",
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Maximum cases to process (default: all)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without writing output",
)
def main(
    input_path: str,
    output_path: str,
    limit: int | None,
    verbose: bool,
    dry_run: bool,
) -> None:
    """Filter MULocBench dataset with solvability and context evaluation.

    Large repos are automatically excluded via EXCLUDED_REPOS in config.
    """
    load_dotenv()

    benchmark_dir = get_benchmark_dir()
    repos_dir = get_repos_dir()

    resolved_input = (
        Path(input_path) if Path(input_path).is_absolute() else (benchmark_dir / input_path)
    )
    resolved_output = (
        Path(output_path) if Path(output_path).is_absolute() else (benchmark_dir / output_path)
    )

    click.echo("=== Dataset Filter Pipeline ===")
    click.echo(f"Input:  {resolved_input}")
    click.echo(f"Output: {resolved_output}")
    click.echo(f"Excluded repos: {len(EXCLUDED_REPOS)}")

    # Load config
    try:
        config = RelaceConfig.from_env()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        click.echo("Set RELACE_API_KEY or SEARCH_API_KEY for LLM evaluation.", err=True)
        sys.exit(1)

    # Load dataset - detect format
    click.echo("\n[1/4] Loading dataset...")
    is_filtered_input = False
    filtered_cases_input: list[FilteredCase] = []
    cases: list[BenchmarkCase] = []

    try:
        # Try to detect format by reading first line
        with open(resolved_input) as f:
            first_line = f.readline().strip()
            if first_line:
                first_obj = json.loads(first_line)
                # Filtered format has "solvability" and "hard_gt" keys
                is_filtered_input = "solvability" in first_obj and "hard_gt" in first_obj

        if is_filtered_input:
            click.echo("  Detected filtered dataset format")
            filtered_cases_input = load_filtered_dataset(str(resolved_input))
            # Apply exclusion for filtered input
            original_count = len(filtered_cases_input)
            excluded_lower = {r.lower() for r in EXCLUDED_REPOS}
            filtered_cases_input = [
                c for c in filtered_cases_input if c.repo.lower() not in excluded_lower
            ]
            if limit:
                filtered_cases_input = filtered_cases_input[:limit]
            excluded_count = original_count - len(filtered_cases_input)
            click.echo(f"  Loaded {len(filtered_cases_input)} filtered cases")
            if excluded_count > 0:
                click.echo(f"  Excluded {excluded_count} cases from large repos")
        else:
            # load_mulocbench already applies EXCLUDED_REPOS by default
            cases = load_mulocbench(
                dataset_path=str(resolved_input),
                limit=limit,
                shuffle=False,
                include_added_files=False,
                require_function_scopes=True,
            )
            click.echo(f"  Loaded {len(cases)} cases (large repos excluded)")
    except Exception as e:
        click.echo(f"Error loading dataset: {e}", err=True)
        sys.exit(1)

    # Setup cache directories
    cache_dir = benchmark_dir / "cache"
    solvability_cache = cache_dir / "solvability"
    relevance_cache = cache_dir / "relevance"

    # Initialize evaluators
    solvability_evaluator = SolvabilityEvaluator(config, cache_dir=solvability_cache)
    _relevance_evaluator = ContextRelevanceEvaluator(
        config,
        threshold=_RELEVANCE_THRESHOLD,
        cache_dir=relevance_cache,
    )

    filtered_cases: list[dict[str, Any]] = []
    rejected_count = 0
    total_input = 0

    # Branch based on input format
    if is_filtered_input:
        # Already filtered - just convert and optionally add context
        click.echo("\n[2/4] Processing filtered cases (skipping solvability)...")
        total_input = len(filtered_cases_input)

        for i, fcase in enumerate(filtered_cases_input):
            progress = f"[{i + 1}/{len(filtered_cases_input)}]"
            if verbose:
                click.echo(f"  {progress} {fcase.id}")
            else:
                click.echo(f"\r  {progress} {fcase.id[:50]}...", nl=False)

            # Convert back to dict, preserving existing data
            entry = {
                "id": fcase.id,
                "query": fcase.query,
                "repo": fcase.repo,
                "base_commit": fcase.base_commit,
                "solvability": fcase.solvability,
                "hard_gt": fcase.hard_gt,
                "soft_context": fcase.soft_context,
            }
            if fcase.issue_url:
                entry["issue_url"] = fcase.issue_url
            if fcase.pr_url:
                entry["pr_url"] = fcase.pr_url

            filtered_cases.append(entry)
            if not verbose:
                click.echo()

        click.echo(f"  Processed: {len(filtered_cases)}")
    else:
        # Original format - full pipeline
        click.echo("\n[2/4] Evaluating solvability...")
        total_input = len(cases)

        for i, case in enumerate(cases):
            progress = f"[{i + 1}/{len(cases)}]"
            if verbose:
                click.echo(f"  {progress} {case.id}")
            else:
                click.echo(f"\r  {progress} {case.id[:50]}...", nl=False)

            # Evaluate solvability
            if not verbose:
                click.echo(" solvability...", nl=False)
            solv_result = solvability_evaluator.evaluate(case.query)

            if not solv_result.solvable or solv_result.confidence < _SOLVABILITY_THRESHOLD:
                rejected_count += 1
                if verbose:
                    click.echo(f"    REJECTED: {solv_result.reject_reason or 'Low confidence'}")
                continue

            # Build output entry
            entry = _build_base_entry(case, solv_result)

            # Normalize to function scopes
            entry = _process_function_scopes(
                case, entry, repos_dir, verbose, show_progress=not verbose
            )

            filtered_cases.append(entry)

            if verbose:
                click.echo(f"    ACCEPTED: confidence={solv_result.confidence:.2f}")
            else:
                click.echo()

        click.echo(f"  Accepted: {len(filtered_cases)}, Rejected: {rejected_count}")

    # Generate report
    click.echo("\n[3/4] Generating report...")
    report = _generate_report(
        cases if not is_filtered_input else [], filtered_cases, _SOLVABILITY_THRESHOLD
    )

    # Write output
    click.echo("\n[4/4] Writing output...")
    if dry_run:
        click.echo("  [DRY RUN] Would write to:")
        click.echo(f"    {resolved_output}")
        click.echo(f"    {resolved_output.with_suffix('.report.json')}")
    else:
        resolved_output.parent.mkdir(parents=True, exist_ok=True)

        with resolved_output.open("w", encoding="utf-8") as f:
            for entry in filtered_cases:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        report_path = resolved_output.with_suffix(".report.json")
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        click.echo(f"  Dataset: {resolved_output}")
        click.echo(f"  Report:  {report_path}")

    click.echo("\n=== Complete ===")
    click.echo(f"  Total input:    {total_input}")
    click.echo(f"  Total output:   {len(filtered_cases)}")
    if total_input > 0:
        click.echo(f"  Filter rate:    {len(filtered_cases) / total_input:.1%}")


def _build_base_entry(
    case: BenchmarkCase,
    solv_result: SolvabilityResult,
) -> dict[str, Any]:
    """Build base entry with solvability info."""
    return {
        "id": case.id,
        "query": case.query,
        "repo": case.repo,
        "base_commit": case.base_commit,
        "issue_url": case.issue_url,
        "pr_url": case.pr_url,
        "solvability": solv_result.to_dict(),
        "hard_gt": [],
        "soft_context": [],
    }


def _process_function_scopes(
    case: BenchmarkCase,
    entry: dict[str, Any],
    repos_dir: Path,
    verbose: bool,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Add function scopes to entry."""
    try:
        if show_progress and not verbose:
            click.echo(" repo...", nl=False)
        repo_path = ensure_repo(
            repos_dir=repos_dir,
            repo=case.repo,
            base_commit=case.base_commit,
            verbose=verbose,
        )

        scopes = normalize_gt_to_function_scopes(repo_path, case.ground_truth_files)
        entry["hard_gt"] = [s.to_dict() for s in scopes]

        if verbose:
            click.echo(f"    Functions: {len(scopes)}")

    except Exception as e:
        if verbose:
            click.echo(f"    Function scope error: {e}")

    return entry


def _generate_report(
    original_cases: list[BenchmarkCase],
    filtered_cases: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    """Generate filtering report."""
    total_hard_gt = sum(len(c.get("hard_gt", [])) for c in filtered_cases)
    total_soft_ctx = sum(len(c.get("soft_context", [])) for c in filtered_cases)

    confidences = [c["solvability"]["confidence"] for c in filtered_cases if "solvability" in c]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    repos = set(c["repo"] for c in filtered_cases)

    return {
        "summary": {
            "total_input": len(original_cases),
            "total_output": len(filtered_cases),
            "filter_rate": len(filtered_cases) / len(original_cases) if original_cases else 0.0,
            "threshold": threshold,
            "avg_confidence": avg_confidence,
            "repos_covered": len(repos),
        },
        "ground_truth_stats": {
            "total_hard_gt_functions": total_hard_gt,
            "total_soft_context_functions": total_soft_ctx,
            "avg_hard_gt_per_case": total_hard_gt / len(filtered_cases) if filtered_cases else 0.0,
            "avg_soft_ctx_per_case": total_soft_ctx / len(filtered_cases)
            if filtered_cases
            else 0.0,
        },
        "repos": sorted(repos),
    }


if __name__ == "__main__":
    main()
