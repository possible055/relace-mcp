import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from relace_mcp.config import RelaceConfig

from .runner import BenchmarkRunner
from .swe_bench import load_swe_bench


@click.command()
@click.option("--limit", default=5, help="Maximum number of cases to run")
@click.option("--output", default="benchmark_results.json", help="Output file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--dry-run", is_flag=True, help="Only load data, don't run searches")
def main(limit: int, output: str, verbose: bool, dry_run: bool) -> None:
    """Run SWE-bench benchmark on fast_search."""
    # Load .env from current directory or parents
    load_dotenv()

    click.echo(f"Loading SWE-bench (limit={limit})...")

    try:
        cases = load_swe_bench(limit=limit)
    except Exception as e:
        click.echo(f"Error loading dataset: {e}", err=True)
        sys.exit(1)

    click.echo(f"Loaded {len(cases)} cases")

    if dry_run:
        click.echo("\n[Dry Run] Cases loaded:")
        for case in cases:
            gt_files = list(case.ground_truth_files.keys())
            click.echo(f"  - {case.id}: {case.repo} ({len(gt_files)} GT files)")
        return

    # Load config from environment
    try:
        config = RelaceConfig.from_env()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        click.echo("Ensure RELACE_API_KEY or RELACE_SEARCH_API_KEY is set.")
        sys.exit(1)

    runner = BenchmarkRunner(config, verbose=verbose)

    click.echo("\nRunning benchmark...")
    summary = runner.run_benchmark(cases)

    # Save results
    output_path = Path(output)
    with open(output_path, "w") as f:
        json.dump(summary.to_dict(), f, indent=2)
    click.echo(f"\nResults saved to {output_path}")

    # Print summary
    click.echo("\n" + "=" * 50)
    click.echo("BENCHMARK SUMMARY")
    click.echo("=" * 50)
    click.echo(f"Total Cases:       {summary.total_cases}")
    click.echo(f"Success Rate:      {summary.success_rate:.1%}")
    click.echo(f"Avg File Recall:   {summary.avg_file_recall:.1%}")
    click.echo(f"Avg File Precision:{summary.avg_file_precision:.1%}")
    click.echo(f"Avg Line Coverage: {summary.avg_line_coverage:.1%}")
    click.echo(f"Avg Line Precision:{summary.avg_line_precision:.1%}")
    click.echo(f"Avg Turns:         {summary.avg_turns:.2f}")
    click.echo(f"Avg Latency:       {summary.avg_latency_ms:.0f}ms")


if __name__ == "__main__":
    main()
