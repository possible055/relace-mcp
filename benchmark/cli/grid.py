import itertools
import json
import os
import subprocess  # nosec B404
import sys
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
    "--turns",
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
    help="Grid values for SEARCH_TEMPERATURE (repeatable, 0.0~1.0 recommended)",
)
@click.option(
    "--search-prompt-file",
    default=None,
    help="Override SEARCH_PROMPT_FILE for all runs (YAML prompt file)",
)
@click.option(
    "--output",
    default=None,
    help=(
        "Output directory prefix (absolute or relative to benchmark/artifacts/results/). "
        "Default: grid_<dataset>_<timestamp>/"
    ),
)
@click.option("--dry-run", is_flag=True, help="Print planned runs without executing")
def main(
    dataset_path: str,
    limit: int | None,
    shuffle: bool,
    seed: int,
    search_max_turns_values: tuple[int, ...],
    search_temperature_values: tuple[float, ...],
    search_prompt_file: str | None,
    output: str | None,
    dry_run: bool,
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

    click.echo(f"Dataset: {resolved_dataset_path}")
    click.echo(f"Planned runs: {len(planned)}")
    click.echo(f"Output dir: {grid_dir}")

    if dry_run:
        for item in planned[:20]:
            click.echo(f"- {item}")
        if len(planned) > 20:
            click.echo(f"... ({len(planned) - 20} more)")
        return

    summaries: list[dict[str, object]] = []
    for i, item in enumerate(planned, 1):
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
            "--no-progress",
            "--output",
            str(item["output_prefix"]),
        ]
        if limit is not None:
            cmd.extend(["--limit", str(limit)])
        cmd.append("--shuffle" if shuffle else "--no-shuffle")

        click.echo(f"[{i}/{len(planned)}] {' '.join(cmd)}")
        completed = subprocess.run(  # nosec B603
            cmd,
            cwd=str(project_root),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            click.echo(completed.stdout)
            click.echo(completed.stderr, err=True)
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
                    "success_rate": report.get("success_rate"),
                    "avg_file_recall": report.get("avg_file_recall"),
                    "avg_file_precision": report.get("avg_file_precision"),
                    "avg_line_coverage": report.get("avg_line_coverage"),
                    "avg_line_precision_matched": report.get("avg_line_precision_matched"),
                    "avg_turns": report.get("avg_turns"),
                    "avg_latency_ms": report.get("avg_latency_ms"),
                },
                "search": (report.get("metadata") or {}).get("search"),
            }
        )

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
