"""Filter pipeline for benchmark datasets.

This command evaluates dataset cases for solvability and optionally builds
soft context from call graphs.
"""

import json
import sys
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv

from relace_mcp.config import RelaceConfig

from ..analysis.call_graph import (
    build_global_index,
    get_context_functions,
    is_wrapper_function,
)
from ..analysis.function_scope import normalize_gt_to_function_scopes
from ..config import (
    DEFAULT_MULOCBENCH_PATH,
    EXCLUDED_REPOS,
    get_benchmark_dir,
    get_cache_dir,
    get_processed_data_dir,
    get_reports_dir,
    get_repos_dir,
)
from ..datasets import DatasetCase, load_dataset
from ..filters.relevance import ContextRelevanceEvaluator
from ..filters.solvability import SolvabilityEvaluator
from ..runner.git import ensure_repo
from ..schemas import (
    SolvabilityInfo,
    generate_output_path,
)

# Internal constants
_SOLVABILITY_THRESHOLD = 0.7
_RELEVANCE_THRESHOLD = 0.5


@click.command()
@click.option(
    "--input",
    "input_path",
    default=DEFAULT_MULOCBENCH_PATH,
    show_default=True,
    help="Input dataset path (relative to benchmark/)",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Output path. Default: data/processed/filter_<timestamp>.jsonl",
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
@click.option(
    "--build-context",
    is_flag=True,
    help="Build soft context from call graph (adds related functions)",
)
def main(
    input_path: str,
    output_path: str | None,
    limit: int | None,
    verbose: bool,
    dry_run: bool,
    build_context: bool,
) -> None:
    """Filter dataset with solvability and context evaluation.

    Large repos are automatically excluded via EXCLUDED_REPOS in config.
    """
    load_dotenv()

    benchmark_dir = get_benchmark_dir()
    repos_dir = get_repos_dir()
    processed_dir = get_processed_data_dir()
    reports_dir = get_reports_dir()

    resolved_input = (
        Path(input_path) if Path(input_path).is_absolute() else (benchmark_dir / input_path)
    )

    # Generate output path with timestamp if not provided
    if output_path:
        resolved_output = (
            Path(output_path) if Path(output_path).is_absolute() else (benchmark_dir / output_path)
        )
    else:
        input_name = Path(input_path).stem
        resolved_output = generate_output_path(processed_dir, "filter", input_name)
        resolved_output = resolved_output.with_suffix(".jsonl")

    click.echo("=== Dataset Filter Pipeline ===")
    click.echo(f"Input:  {resolved_input}")
    click.echo(f"Output: {resolved_output}")
    click.echo(f"Excluded repos: {len(EXCLUDED_REPOS)}")
    click.echo(f"Build context: {build_context}")

    # Load config
    try:
        config = RelaceConfig.from_env()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        click.echo("Set RELACE_API_KEY or SEARCH_API_KEY for LLM evaluation.", err=True)
        sys.exit(1)

    # Load dataset
    click.echo("\n[1/4] Loading dataset...")
    try:
        cases = load_dataset(
            dataset_path=str(resolved_input),
            limit=limit,
            shuffle=False,
        )
        click.echo(f"  Loaded {len(cases)} cases (large repos excluded)")
    except Exception as e:
        click.echo(f"Error loading dataset: {e}", err=True)
        sys.exit(1)

    # Setup cache directories
    cache_dir = get_cache_dir()
    solvability_cache = cache_dir / "solvability"
    relevance_cache = cache_dir / "relevance"

    # Initialize evaluators
    solvability_evaluator = SolvabilityEvaluator(config, cache_dir=solvability_cache)
    relevance_evaluator = ContextRelevanceEvaluator(
        config,
        threshold=_RELEVANCE_THRESHOLD,
        cache_dir=relevance_cache,
    )

    filtered_cases: list[dict[str, Any]] = []
    rejected_count = 0
    total_input = len(cases)

    # Evaluate solvability
    click.echo("\n[2/4] Evaluating solvability...")

    for i, case in enumerate(cases):
        progress = f"[{i + 1}/{len(cases)}]"
        if verbose:
            click.echo(f"  {progress} {case.id}")
        else:
            click.echo(f"\r  {progress} {case.id[:50]}...", nl=False)

        # Check if already has solvability info
        if case.solvability and case.solvability.solvable:
            solv_result = case.solvability
        else:
            if not verbose:
                click.echo(" solvability...", nl=False)
            result = solvability_evaluator.evaluate(case.query)
            solv_result = SolvabilityInfo(
                solvable=result.solvable,
                confidence=result.confidence,
                evidence=result.evidence,
                reject_reason=result.reject_reason,
            )

        if not solv_result.solvable or solv_result.confidence < _SOLVABILITY_THRESHOLD:
            rejected_count += 1
            if verbose:
                click.echo(f"    REJECTED: {solv_result.reject_reason or 'Low confidence'}")
            continue

        # Build output entry
        entry = _build_entry(case, solv_result)

        # Normalize to function scopes if needed
        entry = _process_function_scopes(case, entry, repos_dir, verbose, show_progress=not verbose)

        filtered_cases.append(entry)

        if verbose:
            click.echo(f"    ACCEPTED: confidence={solv_result.confidence:.2f}")
        else:
            click.echo()

    click.echo(f"  Accepted: {len(filtered_cases)}, Rejected: {rejected_count}")

    # Build soft context if requested
    if build_context and filtered_cases:
        click.echo("\n[2.5/4] Building soft context from call graphs...")
        _build_soft_context(filtered_cases, repos_dir, relevance_evaluator, verbose)

    # Generate report
    click.echo("\n[3/4] Generating report...")
    report = _generate_report(total_input, filtered_cases, _SOLVABILITY_THRESHOLD)

    # Write output
    click.echo("\n[4/4] Writing output...")
    if dry_run:
        click.echo("  [DRY RUN] Would write to:")
        click.echo(f"    {resolved_output}")
        click.echo(f"    {reports_dir / resolved_output.stem}.report.json")
    else:
        processed_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        with resolved_output.open("w", encoding="utf-8") as f:
            for entry in filtered_cases:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        report_path = reports_dir / f"{resolved_output.stem}.report.json"
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        click.echo(f"  Dataset: {resolved_output}")
        click.echo(f"  Report:  {report_path}")

    click.echo("\n=== Complete ===")
    click.echo(f"  Total input:    {total_input}")
    click.echo(f"  Total output:   {len(filtered_cases)}")
    if total_input > 0:
        click.echo(f"  Filter rate:    {len(filtered_cases) / total_input:.1%}")


def _build_entry(
    case: DatasetCase,
    solv_result: SolvabilityInfo,
) -> dict[str, Any]:
    """Build output entry from case and solvability result."""
    entry: dict[str, Any] = {
        "id": case.id,
        "query": case.query,
        "repo": case.repo,
        "base_commit": case.base_commit,
        "solvability": solv_result.to_dict(),
        "hard_gt": [gt.to_dict() for gt in case.hard_gt],
        "soft_context": [ctx.to_dict() for ctx in case.soft_context],
    }
    if case.issue_url:
        entry["issue_url"] = case.issue_url
    if case.pr_url:
        entry["pr_url"] = case.pr_url
    return entry


def _process_function_scopes(
    case: DatasetCase,
    entry: dict[str, Any],
    repos_dir: Path,
    verbose: bool,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Add function scopes to entry if needed."""
    # Skip if already has function info
    if entry["hard_gt"] and all(gt.get("function") for gt in entry["hard_gt"]):
        return entry

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


def _build_soft_context(
    filtered_cases: list[dict[str, Any]],
    repos_dir: Path,
    relevance_evaluator: ContextRelevanceEvaluator,
    verbose: bool,
) -> None:
    """Build soft context from call graphs."""
    # Group cases by repo for efficiency
    repo_cases: dict[str, list[int]] = {}
    for idx, entry in enumerate(filtered_cases):
        repo = entry["repo"]
        if repo not in repo_cases:
            repo_cases[repo] = []
        repo_cases[repo].append(idx)

    click.echo(f"  Processing {len(repo_cases)} repositories...")

    for repo_name, case_indices in repo_cases.items():
        if verbose:
            click.echo(f"  Building index for {repo_name}...")

        first_entry = filtered_cases[case_indices[0]]
        try:
            repo_path = ensure_repo(
                repos_dir=repos_dir,
                repo=repo_name,
                base_commit=first_entry["base_commit"],
                verbose=verbose,
            )
        except Exception as e:
            if verbose:
                click.echo(f"    Skip {repo_name}: {e}")
            continue

        graph = build_global_index(repo_path)

        for idx in case_indices:
            entry = filtered_cases[idx]
            hard_gt = entry.get("hard_gt", [])
            if not hard_gt:
                continue

            seed_functions = [gt.get("function", "").split(".")[-1] for gt in hard_gt]
            seed_functions = [f for f in seed_functions if f]

            if not seed_functions:
                continue

            context_funcs = get_context_functions(
                graph,
                seed_functions,
                include_callers=True,
                include_callees=True,
            )

            context_funcs = [f for f in context_funcs if not is_wrapper_function(f)]

            if not context_funcs:
                continue

            query = entry.get("query", "")
            relevance_results = relevance_evaluator.evaluate(query, context_funcs)

            soft_context = []
            for result in relevance_results:
                if result.include:
                    func = next(
                        (
                            f
                            for f in context_funcs
                            if f.name == result.function_name and f.file_path == result.file_path
                        ),
                        None,
                    )
                    if func:
                        soft_context.append(
                            {
                                "path": func.file_path,
                                "function": f"{func.class_name}.{func.name}"
                                if func.class_name
                                else func.name,
                                "range": [func.start_line, func.end_line],
                                "signature": func.signature,
                                "relevance_score": result.relevance_score,
                            }
                        )

            entry["soft_context"] = soft_context

            if verbose:
                click.echo(f"    {entry['id']}: {len(soft_context)} soft context functions")

    total_soft = sum(len(e.get("soft_context", [])) for e in filtered_cases)
    click.echo(f"  Added {total_soft} soft context functions total")


def _generate_report(
    total_input: int,
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
            "total_input": total_input,
            "total_output": len(filtered_cases),
            "filter_rate": len(filtered_cases) / total_input if total_input else 0.0,
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
