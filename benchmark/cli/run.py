import logging
import os
import sys
import warnings
from pathlib import Path

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
    help="Dataset jsonl path (relative to benchmark/ if not absolute)",
)
@click.option(
    "-o",
    "--output",
    default=None,
    help="Output file prefix (default: run_<dataset>_<timestamp>)",
)
@click.option("--limit", default=None, type=int, help="Maximum cases to run (default: all)")
@click.option("--seed", default=0, type=int, help="Random seed for shuffling")
@click.option("--shuffle", is_flag=True, help="Shuffle cases before selecting --limit")
@click.option("--max-turns", default=None, type=int, help="Override SEARCH_MAX_TURNS")
@click.option("--temperature", default=None, type=float, help="Override SEARCH_TEMPERATURE")
@click.option("--prompt-file", default=None, help="Override SEARCH_PROMPT_FILE (YAML)")
@click.option("--timeout", default=None, type=int, help="Per-case timeout in seconds")
@click.option("--fail-fast", default=None, type=int, help="Stop after N consecutive failures")
@click.option("--resume", is_flag=True, help="Resume from checkpoint")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.option("-q", "--quiet", is_flag=True, help="Disable progress bar")
@click.option("--dry-run", is_flag=True, help="Only load data, don't run searches")
@click.option(
    "--search-mode",
    type=click.Choice(["agentic", "indexed"]),
    default="agentic",
    help="Search mode: agentic (fast_search) or indexed (agentic_retrieval)",
)
@click.option(
    "--lsp-tools",
    type=click.Choice(["true", "false", "auto"]),
    default=None,
    help="LSP tools mode: true (all), false (disabled), auto (detect servers)",
)
@click.option(
    "--enabled-tools",
    default=None,
    help="Comma-separated list of enabled internal tools (e.g., view_file,grep_search,bash)",
)
def main(
    dataset_path: str,
    output: str | None,
    limit: int | None,
    seed: int,
    shuffle: bool,
    max_turns: int | None,
    temperature: float | None,
    prompt_file: str | None,
    timeout: int | None,
    fail_fast: int | None,
    resume: bool,
    verbose: bool,
    quiet: bool,
    dry_run: bool,
    search_mode: str,
    lsp_tools: str | None,
    enabled_tools: str | None,
) -> None:
    """Run benchmark on fast_search or agentic_retrieval.

    Large repos are automatically excluded via EXCLUDED_REPOS in config.
    """
    _load_dotenv_from_env_path()

    if prompt_file:
        os.environ["SEARCH_PROMPT_FILE"] = prompt_file
    if max_turns is not None:
        os.environ["SEARCH_MAX_TURNS"] = str(max_turns)
    if temperature is not None:
        os.environ["SEARCH_TEMPERATURE"] = str(temperature)
    if lsp_tools is not None:
        os.environ["SEARCH_LSP_TOOLS"] = lsp_tools
    if enabled_tools is not None:
        os.environ["SEARCH_ENABLED_TOOLS"] = enabled_tools

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
    click.echo(f"  search_mode: {search_mode}")
    click.echo(f"  lsp_tools: {lsp_tools or 'default'}")
    click.echo(f"  enabled_tools: {enabled_tools or 'default'}")
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

    # Determine checkpoint path for resume functionality
    results_dir = get_results_dir()
    checkpoint_path = None
    if resume or timeout or fail_fast:
        # Need output path for checkpoint
        if output:
            output_candidate = Path(output)
            if output_candidate.is_absolute():
                checkpoint_path = output_candidate.with_suffix(".checkpoint.jsonl")
            else:
                checkpoint_path = (results_dir / output_candidate).with_suffix(".checkpoint.jsonl")
        else:
            checkpoint_path = generate_output_path(results_dir, "run", dataset_id).with_suffix(
                ".checkpoint.jsonl"
            )

    if resume and checkpoint_path and not checkpoint_path.exists():
        click.echo(f"Warning: --resume specified but checkpoint not found: {checkpoint_path}")

    runner = BenchmarkRunner(
        config,
        verbose=verbose,
        progress=not quiet,
        checkpoint_path=checkpoint_path,
        case_timeout=timeout,
        fail_fast=fail_fast,
        search_mode=search_mode,
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
            "search_mode": search_mode,
            "lsp_tools": lsp_tools,
            "enabled_tools": enabled_tools,
        },
    )

    # Save results with standardized naming
    reports_dir = get_reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)

    if output:
        output_candidate = Path(output)
        if output_candidate.is_absolute():
            output_path = output_candidate
        else:
            output_path = results_dir / output_candidate
    else:
        output_path = generate_output_path(results_dir, "run", dataset_id)

    jsonl_path = (
        output_path if output_path.suffix == ".jsonl" else output_path.with_suffix(".jsonl")
    )
    report_path = (
        (reports_dir / jsonl_path.relative_to(results_dir)).with_suffix(".report.json")
        if jsonl_path.is_relative_to(results_dir)
        else jsonl_path.with_suffix(".report.json")
    )

    summary.save(output_path, report_path=report_path)

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
