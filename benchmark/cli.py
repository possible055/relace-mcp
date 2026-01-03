import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from relace_mcp.config import RelaceConfig

from .mulocbench import DEFAULT_DATASET_PATH, load_mulocbench
from .runner import BenchmarkRunner


@click.command()
@click.option(
    "--dataset",
    "dataset_path",
    default=DEFAULT_DATASET_PATH,
    show_default=True,
    help="MULocBench jsonl path (relative to benchmark/ if not absolute)",
)
@click.option("--limit", default=5, help="Maximum number of cases to run")
@click.option(
    "--shuffle/--no-shuffle",
    default=True,
    show_default=True,
    help="Shuffle cases before selecting --limit (recommended to reduce bias)",
)
@click.option(
    "--seed",
    default=0,
    show_default=True,
    type=int,
    help="Random seed used when shuffling cases",
)
@click.option(
    "--include-added-files/--exclude-added-files",
    default=False,
    show_default=True,
    help="Include files marked as 'added' in ground truth (usually not present at base_commit)",
)
@click.option(
    "--require-functions/--allow-no-functions",
    default=True,
    show_default=True,
    help="Require at least one function scope in ground truth",
)
@click.option(
    "--output",
    default="results/benchmark_results.json",
    help="Output file path (relative to benchmark/)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Print per-case progress (recommended; benchmarks can take a long time)",
)
@click.option("--dry-run", is_flag=True, help="Only load data, don't run searches")
def main(
    dataset_path: str,
    limit: int,
    shuffle: bool,
    seed: int,
    include_added_files: bool,
    require_functions: bool,
    output: str,
    verbose: bool,
    progress: bool,
    dry_run: bool,
) -> None:
    """Run MULocBench benchmark on fast_search."""
    # Load .env from current directory or parents
    load_dotenv()

    # Resolve output path relative to benchmark directory
    benchmark_dir = Path(__file__).parent
    resolved_dataset_path = (
        Path(dataset_path) if Path(dataset_path).is_absolute() else (benchmark_dir / dataset_path)
    )
    output_path = benchmark_dir / output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Loading MULocBench...")
    click.echo(f"  dataset: {resolved_dataset_path}")
    click.echo(f"  limit:   {limit}")
    click.echo(f"  shuffle: {shuffle}")
    click.echo(f"  seed:    {seed}")

    try:
        cases = load_mulocbench(
            dataset_path=str(resolved_dataset_path),
            limit=limit,
            shuffle=shuffle,
            seed=seed,
            include_added_files=include_added_files,
            require_function_scopes=require_functions,
        )
    except Exception as e:
        click.echo(f"Error loading dataset: {e}", err=True)
        sys.exit(1)

    click.echo(f"Loaded {len(cases)} cases")

    if dry_run:
        click.echo("\n[Dry Run] Cases loaded:")
        for case in cases:
            gt_files = list(case.ground_truth_files.keys())
            click.echo(
                f"  - {case.id}: {case.repo} "
                f"({len(gt_files)} GT files, {len(case.ground_truth_functions)} GT functions)"
            )
        return

    # Load config from environment
    try:
        config = RelaceConfig.from_env()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        click.echo("Ensure RELACE_API_KEY or RELACE_SEARCH_API_KEY is set.")
        sys.exit(1)

    runner = BenchmarkRunner(config, verbose=verbose, progress=progress)

    click.echo("\nRunning benchmark...")
    summary = runner.run_benchmark(
        cases,
        run_config={
            "dataset": "mulocbench",
            "dataset_path": str(resolved_dataset_path),
            "limit": limit,
            "shuffle": shuffle,
            "seed": seed,
            "include_added_files": include_added_files,
            "require_functions": require_functions,
        },
    )

    # Save results
    with open(output_path, "w") as f:
        json.dump(summary.to_dict(), f, indent=2)
    click.echo(f"\nResults saved to {output_path}")

    # Print summary
    click.echo("\n" + "=" * 50)
    click.echo("BENCHMARK SUMMARY")
    click.echo("=" * 50)
    click.echo(f"Total Cases:       {summary.total_cases}")
    click.echo(f"Success Rate:      {summary.success_rate:.1%}")
    click.echo(f"Avg Returned Files:{summary.avg_returned_files:.2f}")
    click.echo(f"Avg GT Files:      {summary.avg_ground_truth_files:.2f}")
    click.echo(f"Avg File Recall:   {summary.avg_file_recall:.1%}")
    click.echo(f"Avg File Precision:{summary.avg_file_precision:.1%}")
    click.echo(f"Avg File F1:       {summary.avg_file_f1:.1%}")
    click.echo(f"Avg Line Coverage: {summary.avg_line_coverage:.1%}")
    click.echo(f"Avg Line Precision:{summary.avg_line_precision:.1%}")
    click.echo(f"Avg Line Prec(M):  {summary.avg_line_precision_matched:.1%}")
    click.echo(f"Avg Line IoU(M):   {summary.avg_line_iou_matched:.1%}")
    click.echo(f"Func Cases:        {summary.function_cases}/{summary.total_cases}")
    click.echo(f"Avg Func Hit Rate: {summary.avg_function_hit_rate:.1%}")
    click.echo(f"Avg Turns:         {summary.avg_turns:.2f}")
    click.echo(f"Avg Latency:       {summary.avg_latency_ms:.0f}ms")
    click.echo(f"Avg Repo Prep:     {summary.avg_repo_prep_ms / 1000:.2f}s")


if __name__ == "__main__":
    main()
