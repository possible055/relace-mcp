import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from relace_mcp.config.bootstrap import initialize_runtime_from_env, reload_runtime_from_env

from ..config.paths import (
    DEFAULT_LOCBENCH_PATH,
    get_benchmark_dir,
    get_experiments_dir,
)
from ..config.settings import EXCLUDED_REPOS
from ..datasets import load_dataset
from ..runner.experiment_paths import (
    build_experiment_name,
    experiment_report_path,
    experiment_results_path,
    resolve_experiment_root,
)


def _load_benchmark_config():
    """Load config for running search benchmarks.

    Note: RELACE_API_KEY is only required when SEARCH_PROVIDER=relace. For other
    providers, SearchLLMClient will use SEARCH_API_KEY.
    """
    from relace_mcp.config import RelaceConfig
    from relace_mcp.config import settings as _settings

    search_provider = (_settings.SEARCH_PROVIDER or _settings.RELACE_PROVIDER).lower()
    if search_provider == _settings.RELACE_PROVIDER:
        return RelaceConfig.from_env()

    return RelaceConfig(
        api_key=_settings.RELACE_API_KEY,
        base_dir=None,
        default_encoding=_settings.RELACE_DEFAULT_ENCODING,
        extra_paths=_settings.MCP_EXTRA_PATHS,
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
    help="Experiment directory name/path (default uses the standard experiment template)",
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
    "--trace",
    is_flag=True,
    help="Save per-case trace JSONL (turns_log) and a run-level events JSONL derived from trace",
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
@click.option(
    "--experiment-type",
    type=click.Choice(["run", "trial"]),
    default="run",
    hidden=True,
)
@click.option(
    "--parent-experiment-root",
    default=None,
    hidden=True,
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
    experiment_type: str,
    parent_experiment_root: str | None,
) -> None:
    """Run benchmark on agentic_search or agentic_retrieval.

    Large repos are automatically excluded via EXCLUDED_REPOS in config.
    """
    from relace_mcp.config import settings as _settings

    initialize_runtime_from_env()

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
    reload_runtime_from_env()

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
            "For non-Relace search: set SEARCH_PROVIDER, SEARCH_ENDPOINT, "
            "SEARCH_MODEL, and SEARCH_API_KEY."
        )
        sys.exit(1)

    experiments_dir = get_experiments_dir()
    checkpoint_path = None

    # Generate experiment root once upfront to ensure all outputs land together.
    if output:
        experiment_root = resolve_experiment_root(output)
    else:
        provider = (_settings.SEARCH_PROVIDER or _settings.RELACE_PROVIDER).lower()
        experiment_name = build_experiment_name(
            experiment_type,
            dataset_id,
            search_mode,
            provider,
            timestamp=datetime.now(UTC),
        )
        experiment_root = experiments_dir / experiment_name

    experiment_root.mkdir(parents=True, exist_ok=True)
    results_path = experiment_results_path(experiment_root)
    report_path = experiment_report_path(experiment_root)

    if resume or timeout or fail_fast:
        checkpoint_path = results_path.with_name("checkpoint.jsonl")

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
        artifact_root=experiment_root,
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
            "experiment_type": experiment_type,
            "parent_experiment_root": parent_experiment_root,
        },
    )

    summary.save(results_path, report_path=report_path)

    click.echo("\nResults saved to:")
    click.echo(f"  - experiment: {experiment_root}")
    click.echo(f"  - {results_path}")
    click.echo(f"  - {report_path}")
    if trace and runner.trace_recorder is not None and runner.trace_recorder.traces_dir is not None:
        click.echo(f"  - traces: {runner.trace_recorder.traces_dir}")
    if (
        trace
        and runner.trace_recorder is not None
        and runner.trace_recorder.events_path is not None
    ):
        click.echo(f"  - events: {runner.trace_recorder.events_path}")

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
