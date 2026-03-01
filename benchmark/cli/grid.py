import itertools
import json
import os
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

import click

from ..config import DEFAULT_LOCBENCH_PATH, get_benchmark_dir, get_reports_dir, get_results_dir
from ..schemas import generate_output_path


def _format_float_for_filename(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text.replace(".", "p")


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
    help="Output directory prefix (default: grid_<dataset>_<timestamp>/)",
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

    results_dir = get_results_dir()
    default_grid_root = generate_output_path(results_dir, "grid", dataset_id)
    grid_root = (
        (Path(output) if Path(output).is_absolute() else (results_dir / output))
        if output
        else default_grid_root
    )

    grid_dir = grid_root
    grid_dir.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[2]

    planned: list[dict[str, object]] = []
    for turns, temp in itertools.product(
        search_max_turns_values,
        search_temperature_values,
    ):
        name_parts = [
            f"t{turns}",
            f"temp{_format_float_for_filename(temp)}",
        ]
        run_name = "__".join(name_parts)
        output_prefix = grid_dir / run_name
        planned.append(
            {
                "search_max_turns": turns,
                "search_temperature": temp,
                "output_prefix": str(output_prefix),
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

    summaries: list[dict[str, object]] = []
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
            str(item["output_prefix"]),
            "--search-mode",
            search_mode,
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

        output_prefix = Path(str(item["output_prefix"]))
        jsonl_path = (
            output_prefix
            if output_prefix.suffix == ".jsonl"
            else output_prefix.with_suffix(".jsonl")
        )
        report_path = (
            (get_reports_dir() / jsonl_path.relative_to(results_dir)).with_suffix(".report.json")
            if jsonl_path.is_relative_to(results_dir)
            else jsonl_path.with_suffix(".report.json")
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))

        summaries.append(
            {
                "config": item,
                "paths": {
                    "jsonl": str(jsonl_path),
                    "report": str(report_path),
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
                "search": (report.get("metadata") or {}).get("search"),
            }
        )

    # Final summary
    elapsed = time.perf_counter() - wall_start
    mins, secs = divmod(int(elapsed), 60)
    click.echo(f"\nGrid completed: {total_runs} runs in {mins:02d}:{secs:02d}")

    report_out = get_reports_dir() / f"{grid_dir.name}.grid.json"
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(
        json.dumps(
            {
                "dataset_path": str(resolved_dataset_path),
                "grid_dir": str(grid_dir),
                "runs": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    click.echo(f"\nGrid summary saved to: {report_out}")


if __name__ == "__main__":
    main()
