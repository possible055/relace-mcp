import itertools
import json
import os
import subprocess  # nosec B404
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from .._config.paths import DEFAULT_LOCBENCH_PATH, get_benchmark_dir, get_experiments_dir
from ..runner.experiment_paths import (
    build_experiment_name,
    build_trial_name,
    experiment_report_path,
    experiment_results_path,
    grid_runs_dir,
    resolve_experiment_root,
)
from ..runner.results import write_report_json


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
    benchmark_dir = get_benchmark_dir()
    resolved_dataset_path = (
        Path(dataset_path) if Path(dataset_path).is_absolute() else (benchmark_dir / dataset_path)
    )
    dataset_id = resolved_dataset_path.stem
    provider = os.getenv("SEARCH_PROVIDER", "relace").strip().lower() or "relace"
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
    grid_dir = grid_root
    grid_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = grid_runs_dir(grid_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[2]

    planned: list[dict[str, object]] = []
    for turns, temp in itertools.product(
        search_max_turns_values,
        search_temperature_values,
    ):
        run_name = build_trial_name(turns, temp)
        experiment_root = runs_dir / run_name
        planned.append(
            {
                "search_max_turns": turns,
                "search_temperature": temp,
                "experiment_root": str(experiment_root),
            }
        )

    # Display paths relative to benchmark_dir for cleaner output
    try:
        dataset_display = resolved_dataset_path.relative_to(benchmark_dir)
    except ValueError:
        dataset_display = resolved_dataset_path
    try:
        output_display = grid_dir.relative_to(benchmark_dir)
    except ValueError:
        output_display = grid_dir

    click.echo(f"Dataset: {dataset_display}")
    click.echo(f"Planned runs: {len(planned)}")
    click.echo(f"Output dir: {output_display}")

    if dry_run:
        for item in planned[:20]:
            click.echo(f"- {item}")
        if len(planned) > 20:
            click.echo(f"... ({len(planned) - 20} more)")
        return

    summaries: list[dict[str, Any]] = []
    first_metadata: dict[str, Any] | None = None
    total_runs = len(planned)
    wall_start = time.perf_counter()

    for i, item in enumerate(planned, 1):
        # Print run header
        config_info = f"max_turns={item['search_max_turns']} temp={item['search_temperature']}"
        click.echo(f"\n[Run {i}/{total_runs}] {config_info}")

        env = dict(os.environ)
        env["SEARCH_MAX_TURNS"] = str(item["search_max_turns"])
        env["SEARCH_TEMPERATURE"] = str(item["search_temperature"])
        if search_prompt_file:
            env["SEARCH_PROMPT_FILE"] = search_prompt_file

        cmd = [
            sys.executable,
            "-m",
            "benchmark.cli.run",
            "--dataset",
            dataset_path,
            "--seed",
            str(seed),
            "--output",
            str(item["experiment_root"]),
            "--search-mode",
            search_mode,
            "--experiment-type",
            "trial",
            "--parent-experiment-root",
            str(grid_dir),
        ]
        if lsp_tools is not None:
            cmd.extend(["--lsp-tools", lsp_tools])
        if bash_tools is not None:
            cmd.extend(["--bash-tools", bash_tools])
        if limit is not None:
            cmd.extend(["--limit", str(limit)])
        if shuffle:
            cmd.append("--shuffle")

        # Let subprocess output directly (progress bar visible)
        completed = subprocess.run(  # nosec B603
            cmd,
            cwd=str(project_root),
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)

        experiment_root = Path(str(item["experiment_root"]))
        jsonl_path = experiment_results_path(experiment_root)
        report_path = experiment_report_path(experiment_root)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        if first_metadata is None and isinstance(report_metadata, dict):
            first_metadata = report_metadata

        summaries.append(
            {
                "config": {
                    "search_max_turns": item["search_max_turns"],
                    "search_temperature": item["search_temperature"],
                },
                "paths": {
                    "experiment_root": str(experiment_root),
                    "results_path": str(jsonl_path),
                    "report_path": str(report_path),
                },
                "metrics": {
                    "completion_rate": report.get("completion_rate"),
                    "avg_quality_score": report.get("avg_quality_score"),
                    "avg_file_recall": report.get("avg_file_recall"),
                    "avg_file_precision": report.get("avg_file_precision"),
                    "avg_line_coverage": report.get("avg_line_coverage"),
                    "avg_line_precision_matched": report.get("avg_line_precision_matched"),
                    "avg_turns": report.get("avg_turns"),
                    "avg_latency_s": report.get("avg_latency_s"),
                },
                "search": report_metadata.get("search")
                if isinstance(report_metadata, dict)
                else None,
            }
        )

    # Final summary
    elapsed = time.perf_counter() - wall_start
    mins, secs = divmod(int(elapsed), 60)
    click.echo(f"\nGrid completed: {total_runs} runs in {mins:02d}:{secs:02d}")

    best_trial = max(
        summaries,
        key=lambda item: item.get("metrics", {}).get("avg_file_recall", 0) or 0,
    )
    grid_completed_at = datetime.now(UTC)
    child_run = first_metadata.get("run") if isinstance(first_metadata, dict) else {}
    grid_report = {
        "metadata": {
            **(first_metadata or {}),
            "run": {
                "dataset": dataset_id,
                "dataset_path": str(resolved_dataset_path),
                "limit": limit,
                "shuffle": shuffle,
                "seed": seed,
                "search_mode": search_mode,
                "lsp_tools": lsp_tools,
                "bash_tools": bash_tools,
                "cases_loaded": child_run.get("cases_loaded")
                if isinstance(child_run, dict)
                else None,
                "started_at_utc": grid_started_at.isoformat(),
                "completed_at_utc": grid_completed_at.isoformat(),
                "duration_s": round(elapsed, 1),
            },
            "experiment": {
                "type": "grid",
                "name": grid_dir.name,
                "root": str(grid_dir),
                "parent_root": None,
            },
            "artifacts": {
                "experiment_root": str(grid_dir),
                "reports_dir": str(grid_dir / "reports"),
                "runs_dir": str(runs_dir),
            },
        },
        "grid": {
            "objective": "avg_file_recall",
            "search_space": {
                "search_max_turns": sorted(set(search_max_turns_values)),
                "search_temperature": sorted(set(search_temperature_values)),
            },
            "trial_count": len(summaries),
            "trials": summaries,
            "best_trial": best_trial,
        },
    }
    report_out = experiment_report_path(grid_dir)
    write_report_json(grid_report, report_out)

    click.echo(f"\nGrid summary saved to: {report_out}")


if __name__ == "__main__":
    main()
