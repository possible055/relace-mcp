import logging
import os
import sys
import warnings
from pathlib import Path
from typing import Literal

import click
from dotenv import load_dotenv

from ..config import (
    DEFAULT_LOCBENCH_PATH,
    EXCLUDED_REPOS,
    get_benchmark_dir,
    get_reports_dir,
    get_results_dir,
)
from ..datasets import load_dataset
from ..schemas import generate_output_path

logger = logging.getLogger(__name__)


def _load_dotenv_from_env_path() -> None:
    """Load .env file from MCP_DOTENV_PATH or default locations.

    Priority:
    1. MCP_DOTENV_PATH environment variable (explicit path)
    2. RELACE_DOTENV_PATH environment variable (deprecated alias)
    3. Default dotenv search (current directory and parents)
    """
    dotenv_path = os.getenv("MCP_DOTENV_PATH", "").strip()
    if not dotenv_path:
        legacy_path = os.getenv("RELACE_DOTENV_PATH", "").strip()
        if legacy_path:
            logger.warning("RELACE_DOTENV_PATH is deprecated; use MCP_DOTENV_PATH instead")
            dotenv_path = legacy_path
    if dotenv_path:
        path = Path(dotenv_path).expanduser()
        if path.exists():
            load_dotenv(path)
            logger.info("Loaded .env from MCP_DOTENV_PATH")
        else:
            logger.warning("MCP_DOTENV_PATH does not exist")
            warnings.warn(
                f"MCP_DOTENV_PATH does not exist: {dotenv_path}", RuntimeWarning, stacklevel=2
            )
            load_dotenv()  # Fallback to default
    else:
        load_dotenv()


def _load_benchmark_config():
    """Load config for running search benchmarks.

    Note: RELACE_API_KEY is only required when SEARCH_PROVIDER=relace. For other
    providers, SearchLLMClient will use SEARCH_API_KEY / OPENAI_API_KEY / etc.
    """
    from relace_mcp.config import RelaceConfig
    from relace_mcp.config.compat import getenv_with_fallback
    from relace_mcp.config.settings import RELACE_DEFAULT_ENCODING

    search_provider = getenv_with_fallback("SEARCH_PROVIDER", "RELACE_SEARCH_PROVIDER").strip()
    search_provider = (search_provider or "relace").lower()

    relace_api_key = os.getenv("RELACE_API_KEY", "").strip()
    if search_provider == "relace":
        return RelaceConfig.from_env()

    # Non-relace providers: allow running without RELACE_API_KEY.
    return RelaceConfig(
        api_key=relace_api_key, base_dir=None, default_encoding=RELACE_DEFAULT_ENCODING
    )


@click.command()
@click.option(
    "--dataset",
    "dataset_path",
    default=DEFAULT_LOCBENCH_PATH,
    show_default=True,
    help="Dataset jsonl path (relative to benchmark/ if not absolute)",
)
@click.option("--limit", default=None, type=int, help="Maximum cases to run (default: all)")
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
    "--output",
    default=None,
    help="Output file prefix (relative to benchmark/artifacts/results/). Default: run_<timestamp>",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Print per-case progress (recommended; benchmarks can take a long time)",
)
@click.option("--dry-run", is_flag=True, help="Only load data, don't run searches")
@click.option(
    "--harness",
    "harness_type",
    type=click.Choice(["fast", "dual"]),
    default=None,
    help="Search harness type (default: from SEARCH_HARNESS_TYPE env or 'dual')",
)
@click.option(
    "--search-max-turns",
    default=None,
    type=int,
    help="Override SEARCH_MAX_TURNS for this run",
)
@click.option(
    "--search-temperature",
    default=None,
    type=float,
    help="Override SEARCH_TEMPERATURE for this run",
)
@click.option(
    "--merger-temperature",
    default=None,
    type=float,
    help="Override MERGER_TEMPERATURE for this run (dual harness merge step)",
)
@click.option(
    "--dual-channel-turns",
    default=None,
    type=int,
    help="Override SEARCH_DUAL_CHANNEL_TURNS for this run (dual harness per-channel turns)",
)
@click.option(
    "--search-prompt-file",
    default=None,
    help="Override SEARCH_PROMPT_FILE for this run (YAML prompt file)",
)
def main(
    dataset_path: str,
    limit: int,
    shuffle: bool,
    seed: int,
    output: str,
    verbose: bool,
    progress: bool,
    dry_run: bool,
    harness_type: str | None,
    search_max_turns: int | None,
    search_temperature: float | None,
    merger_temperature: float | None,
    dual_channel_turns: int | None,
    search_prompt_file: str | None,
) -> None:
    """Run benchmark on fast_search.

    Large repos are automatically excluded via EXCLUDED_REPOS in config.
    """
    _load_dotenv_from_env_path()

    if search_prompt_file:
        os.environ["SEARCH_PROMPT_FILE"] = search_prompt_file
    if search_max_turns is not None:
        os.environ["SEARCH_MAX_TURNS"] = str(search_max_turns)
    if search_temperature is not None:
        os.environ["SEARCH_TEMPERATURE"] = str(search_temperature)
    if merger_temperature is not None:
        os.environ["MERGER_TEMPERATURE"] = str(merger_temperature)
    if dual_channel_turns is not None:
        os.environ["SEARCH_DUAL_CHANNEL_TURNS"] = str(dual_channel_turns)

    from relace_mcp.config.settings import SEARCH_HARNESS_TYPE

    from ..runner.executor import BenchmarkRunner

    benchmark_dir = get_benchmark_dir()
    resolved_dataset_path = (
        Path(dataset_path) if Path(dataset_path).is_absolute() else (benchmark_dir / dataset_path)
    )
    dataset_id = resolved_dataset_path.stem
    click.echo("Loading dataset...")
    click.echo(f"  dataset: {resolved_dataset_path}")
    click.echo(f"  limit:   {limit if limit is not None else 'all'}")
    click.echo(f"  shuffle: {shuffle}")
    click.echo(f"  seed:    {seed}")
    click.echo(f"  excluded repos: {len(EXCLUDED_REPOS)}")

    try:
        cases = load_dataset(
            dataset_path=str(resolved_dataset_path),
            limit=limit,
            shuffle=shuffle,
            seed=seed,
            stratified=True,
        )
    except Exception as e:
        click.echo(f"Error loading dataset: {e}", err=True)
        sys.exit(1)

    click.echo(f"Loaded {len(cases)} cases (large repos excluded)")

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
        config = _load_benchmark_config()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        click.echo(
            "For Relace search: set RELACE_API_KEY.\n"
            "For non-Relace search: set SEARCH_PROVIDER and its API key "
            "(e.g. SEARCH_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY)."
        )
        sys.exit(1)

    # Resolve harness type from env if not specified via CLI
    effective_harness_type: Literal["fast", "dual"] = (
        harness_type if harness_type in ("fast", "dual") else SEARCH_HARNESS_TYPE  # type: ignore[assignment]
    )

    runner = BenchmarkRunner(
        config,
        verbose=verbose,
        progress=progress,
        harness_type=effective_harness_type,
    )

    click.echo("\nRunning benchmark...")
    summary = runner.run_benchmark(
        cases,
        run_config={
            "dataset": dataset_id,
            "dataset_path": str(resolved_dataset_path),
            "limit": limit,
            "shuffle": shuffle,
            "seed": seed,
            "harness_type": effective_harness_type,
        },
    )

    # Save results with standardized naming
    benchmark_dir = get_benchmark_dir()
    results_dir = get_results_dir()
    reports_dir = get_reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)

    if output:
        if Path(output).is_absolute():
            output_path = Path(output)
        else:
            output_path = benchmark_dir / output
    else:
        output_path = generate_output_path(results_dir, "run", dataset_id)

    # summary.save handles directory creation and dual-file extensions (.jsonl, .report.json)
    summary.save(output_path)

    jsonl_path = (
        output_path if output_path.suffix == ".jsonl" else output_path.with_suffix(".jsonl")
    )
    report_path = jsonl_path.with_suffix(".report.json")

    click.echo("\nResults saved to:")
    click.echo(f"  - {jsonl_path}")
    click.echo(f"  - {report_path}")

    # Print summary
    click.echo("\n" + "=" * 50)
    click.echo("BENCHMARK SUMMARY")
    click.echo("=" * 50)
    s = summary.stats
    click.echo(f"Total Cases:       {summary.total_cases}")
    click.echo(f"Success Rate:      {s['success_rate']:.1%}")
    click.echo(f"Avg Returned Files:{s['avg_returned_files']:.2f}")
    click.echo(f"Avg GT Files:      {s['avg_ground_truth_files']:.2f}")
    click.echo(f"Avg File Recall:   {s['avg_file_recall']:.1%}")
    click.echo(f"Avg File Precision:{s['avg_file_precision']:.1%}")
    click.echo(f"Avg Target Line Cov:{s['avg_line_coverage']:.1%}")
    click.echo(f"Avg Target Line Prec(M): {s['avg_line_precision_matched']:.1%}")
    click.echo(f"Avg Context Line Cov:{s['avg_context_line_coverage']:.1%}")
    click.echo(f"Avg Context Line Prec(M): {s['avg_context_line_precision_matched']:.1%}")
    click.echo(f"Func Cases:        {int(s['function_cases'])}/{summary.total_cases}")
    click.echo(f"Avg Func Hit Rate: {s['avg_function_hit_rate']:.1%}")
    click.echo(f"Avg Turns:         {s['avg_turns']:.2f}")
    click.echo(f"Avg Latency:       {s['avg_latency_ms']:.0f}ms")


if __name__ == "__main__":
    main()
