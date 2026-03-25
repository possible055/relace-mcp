import itertools
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from relace_mcp.config.bootstrap import initialize_runtime_from_env

from ..config.paths import DEFAULT_LOCBENCH_PATH, get_benchmark_dir, get_experiments_dir
from ..datasets import load_dataset
from ..experiments.layout import (
    build_experiment_name,
    build_trial_name,
    experiment_report_path,
    experiment_results_path,
    grid_runs_dir,
    manifest_path,
    resolve_experiment_root,
    state_path,
    summary_path,
)
from ..experiments.models import ExperimentState
from ..experiments.runner import BenchmarkRunner
from ..experiments.store import ExperimentStore
from .run import _load_benchmark_config


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
    help="Grid experiment directory name/path (default uses the standard experiment template)",
)
@click.option("--limit", default=None, type=int, help="Maximum cases to run (default: all)")
@click.option("--seed", default=0, type=int, help="Random seed for shuffling")
@click.option("--shuffle", is_flag=True, help="Shuffle cases before selecting --limit")
@click.option(
    "--max-turns",
    "search_max_turns_values",
    multiple=True,
    type=int,
    required=True,
    help="Grid values for SEARCH_MAX_TURNS (repeatable)",
)
@click.option(
    "--temperatures",
    "search_temperature_values",
    multiple=True,
    type=float,
    required=True,
    help="Grid values for SEARCH_TEMPERATURE (repeatable)",
)
@click.option(
    "--prompt-file",
    "search_prompt_file",
    default=None,
    help="Override SEARCH_PROMPT_FILE for all runs (YAML)",
)
@click.option("--dry-run", is_flag=True, help="Print planned runs without executing")
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
    search_max_turns_values: tuple[int, ...],
    search_temperature_values: tuple[float, ...],
    search_prompt_file: str | None,
    dry_run: bool,
    search_mode: str,
    lsp_tools: str | None,
    bash_tools: str | None,
) -> None:
    from relace_mcp.config import settings as _settings

    initialize_runtime_from_env()

    benchmark_dir = get_benchmark_dir()
    resolved_dataset_path = (
        Path(dataset_path) if Path(dataset_path).is_absolute() else (benchmark_dir / dataset_path)
    )
    dataset_id = resolved_dataset_path.stem
    provider = (_settings.SEARCH_PROVIDER or _settings.RELACE_PROVIDER).lower()
    grid_started_at = datetime.now(UTC)

    experiments_dir = get_experiments_dir()
    if output:
        grid_root = resolve_experiment_root(output)
    else:
        grid_root = experiments_dir / build_experiment_name(
            "grid",
            dataset_id,
            search_mode,
            provider,
            objective="avg-file-recall",
            timestamp=grid_started_at,
        )
    grid_root.mkdir(parents=True, exist_ok=True)
    trials_root = grid_runs_dir(grid_root)
    trials_root.mkdir(parents=True, exist_ok=True)

    planned: list[dict[str, object]] = []
    for turns, temp in itertools.product(search_max_turns_values, search_temperature_values):
        planned.append(
            {
                "search_max_turns": turns,
                "search_temperature": temp,
                "experiment_root": str(trials_root / build_trial_name(turns, temp)),
            }
        )

    try:
        dataset_display = resolved_dataset_path.relative_to(benchmark_dir)
    except ValueError:
        dataset_display = resolved_dataset_path
    try:
        output_display = grid_root.relative_to(benchmark_dir)
    except ValueError:
        output_display = grid_root

    click.echo(f"Dataset: {dataset_display}")
    click.echo(f"Planned runs: {len(planned)}")
    click.echo(f"Output dir: {output_display}")

    if dry_run:
        for item in planned[:20]:
            click.echo(f"- {item}")
        if len(planned) > 20:
            click.echo(f"... ({len(planned) - 20} more)")
        return

    cases = load_dataset(
        dataset_path=str(resolved_dataset_path),
        limit=limit,
        shuffle=shuffle,
        seed=seed,
        stratified=True,
    )
    config = _load_benchmark_config()
    store = ExperimentStore(get_experiments_dir())
    store.create(
        experiment_root=grid_root,
        kind="grid",
        cases=[],
        config=config,
        run_config={
            "dataset": dataset_id,
            "dataset_path": str(resolved_dataset_path),
            "limit": limit,
            "shuffle": shuffle,
            "seed": seed,
            "search_mode": search_mode,
            "lsp_tools": lsp_tools,
            "bash_tools": bash_tools,
            "experiment_type": "grid",
            "tags": ["grid"],
        },
    )

    original_env = {
        "SEARCH_MAX_TURNS": os.environ.get("SEARCH_MAX_TURNS"),
        "SEARCH_TEMPERATURE": os.environ.get("SEARCH_TEMPERATURE"),
        "SEARCH_PROMPT_FILE": os.environ.get("SEARCH_PROMPT_FILE"),
        "SEARCH_LSP_TOOLS": os.environ.get("SEARCH_LSP_TOOLS"),
        "SEARCH_BASH_TOOLS": os.environ.get("SEARCH_BASH_TOOLS"),
    }

    summaries: list[dict[str, Any]] = []
    total_runs = len(planned)
    wall_start = time.perf_counter()

    try:
        for i, item in enumerate(planned, 1):
            turns = int(item["search_max_turns"])
            temperature = float(item["search_temperature"])
            experiment_root = Path(str(item["experiment_root"]))
            click.echo(f"\n[Run {i}/{total_runs}] max_turns={turns} temp={temperature}")

            os.environ["SEARCH_MAX_TURNS"] = str(turns)
            os.environ["SEARCH_TEMPERATURE"] = str(temperature)
            if search_prompt_file:
                os.environ["SEARCH_PROMPT_FILE"] = search_prompt_file
            if lsp_tools is not None:
                os.environ["SEARCH_LSP_TOOLS"] = lsp_tools
            if bash_tools is not None:
                os.environ["SEARCH_BASH_TOOLS"] = bash_tools

            runner = BenchmarkRunner(
                config,
                progress=True,
                search_mode=search_mode,
                artifact_root=experiment_root,
            )
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
                    "experiment_type": "trial",
                    "parent_experiment_root": str(grid_root),
                },
            )
            summary.save(
                experiment_results_path(experiment_root),
                report_path=experiment_report_path(experiment_root),
            )
            summaries.append(
                {
                    "config": {
                        "search_max_turns": turns,
                        "search_temperature": temperature,
                    },
                    "paths": {
                        "experiment_root": str(experiment_root),
                        "results_path": str(experiment_results_path(experiment_root)),
                        "summary_path": str(summary_path(experiment_root)),
                    },
                    "stats": summary.stats,
                }
            )
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    elapsed = time.perf_counter() - wall_start
    mins, secs = divmod(int(elapsed), 60)
    click.echo(f"\nGrid completed: {total_runs} runs in {mins:02d}:{secs:02d}")

    best_trial = max(
        summaries,
        key=lambda item: float(item.get("stats", {}).get("avg_file_recall", 0.0) or 0.0),
    )
    grid_summary = {
        "metadata": {
            "experiment": {
                "id": grid_root.name,
                "type": "grid",
                "name": grid_root.name,
                "root": str(grid_root),
                "parent_root": None,
            },
            "dataset": {
                "name": dataset_id,
                "dataset_path": str(resolved_dataset_path),
                "case_count": len(cases),
            },
            "run": {
                "started_at_utc": grid_started_at.isoformat(),
                "completed_at_utc": datetime.now(UTC).isoformat(),
                "duration_s": round(elapsed, 1),
                "search_mode": search_mode,
            },
        },
        "manifest": json.loads(manifest_path(grid_root).read_text("utf-8")),
        "state": ExperimentState(
            status="completed",
            total_cases=len(planned),
            completed_cases=len(planned),
            failed_cases=0,
        ).to_dict(),
        "stats": {
            "trial_count": len(planned),
            "best_avg_file_recall": best_trial["stats"].get("avg_file_recall", 0.0),
        },
        "trials": summaries,
        "best_trial": best_trial,
    }
    summary_path(grid_root).write_text(
        json.dumps(grid_summary, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    state_path(grid_root).write_text(
        json.dumps(
            ExperimentState(
                status="completed",
                total_cases=len(planned),
                completed_cases=len(planned),
                failed_cases=0,
            ).to_dict(),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "utf-8",
    )

    click.echo(f"\nGrid summary saved to: {summary_path(grid_root)}")


if __name__ == "__main__":
    main()
