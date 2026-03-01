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
    2. Default dotenv search (current directory and parents)
    """
    dotenv_path = os.getenv("MCP_DOTENV_PATH", "").strip()
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
    from relace_mcp.config.settings import RELACE_DEFAULT_ENCODING

    search_provider = os.getenv("SEARCH_PROVIDER", "").strip()
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
    "--trace", is_flag=True, help="Save per-case trace JSONL (reconstructed from relace.log)"
)
@click.option(
    "--search-mode",
    type=click.Choice(["agentic", "indexed"]),
    default="agentic",
    help="Search mode: agentic (agentic_search) or indexed (agentic_retrieval)",
)
@click.option(
    "--lsp-tools",
    type=click.Choice(["true", "false"]),
    default=None,
    help="LSP tools toggle: true (enabled), false (disabled)",
)
@click.option(
    "--bash-tools",
    type=click.Choice(["true", "false"]),
    default=None,
    help="Bash tool toggle: true (enabled), false (disabled)",
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
    trace: bool,
    search_mode: str,
    lsp_tools: str | None,
    bash_tools: str | None,
) -> None:
    """Run benchmark on agentic_search or agentic_retrieval.

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
    if bash_tools is not None:
        os.environ["SEARCH_BASH_TOOLS"] = bash_tools
    if search_mode == "indexed":
        os.environ.setdefault("MCP_RETRIEVAL_BACKEND", "auto")

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
    click.echo(f"  bash_tools: {bash_tools or 'default'}")
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

    # Generate output path once upfront to ensure checkpoint and results share the same path
    if output:
        output_candidate = Path(output)
        if output_candidate.is_absolute():
            resolved_output_path = output_candidate
        else:
            resolved_output_path = results_dir / output_candidate
    else:
        resolved_output_path = generate_output_path(results_dir, "run", dataset_id)

    if resume or timeout or fail_fast:
        checkpoint_path = resolved_output_path.with_suffix(".checkpoint.jsonl")

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
        resume=resume,
        trace=trace,
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
            "bash_tools": bash_tools,
        },
    )

    # Save results with standardized naming
    reports_dir = get_reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)

    output_path = resolved_output_path

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
    if trace and hasattr(runner, "_traces_dir") and runner._traces_dir:
        click.echo(f"  - traces: {runner._traces_dir}")

    # Print summary
    click.echo("\n" + "=" * 50)
    click.echo("BENCHMARK SUMMARY")
    click.echo("=" * 50)
    s = summary.stats
    click.echo(f"Total Cases:       {summary.total_cases}")
    click.echo(f"Completion Rate:   {s['completion_rate']:.1%}")
    click.echo(f"Quality Score:     {s['avg_quality_score']:.1%}")
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
    click.echo(f"Avg Latency:       {s['avg_latency_s']:.1f}s")


if __name__ == "__main__":
    main()
