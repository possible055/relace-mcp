import json
from pathlib import Path

import click

from ..config import get_reports_dir


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_grid_report(path: Path) -> list[dict]:
    data = _load_report(path)
    return data.get("runs", [])


def _extract_metrics(report: dict) -> dict:
    if "runs" in report:
        return {}
    return {
        "success_rate": report.get("success_rate", 0),
        "avg_file_recall": report.get("avg_file_recall", 0),
        "avg_file_precision": report.get("avg_file_precision", 0),
        "avg_line_coverage": report.get("avg_line_coverage", 0),
        "avg_line_precision_matched": report.get("avg_line_precision_matched", 0),
        "avg_turns": report.get("avg_turns", 0),
        "avg_latency_ms": report.get("avg_latency_ms", 0),
    }


def _find_best_from_grid(runs: list[dict], metric: str = "avg_file_recall") -> dict | None:
    if not runs:
        return None
    best = max(runs, key=lambda r: r.get("metrics", {}).get(metric, 0))
    return best


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _generate_markdown_comparison(reports: list[tuple[str, dict]]) -> str:
    lines = ["# Benchmark Comparison Report", ""]

    lines.append("| Run | Success | F.Recall | F.Prec | L.Cov | L.Prec(M) | Turns | Latency |")
    lines.append("|-----|---------|----------|--------|-------|-----------|-------|---------|")

    for name, report in reports:
        m = _extract_metrics(report)
        if not m:
            continue
        lines.append(
            f"| {name} | "
            f"{_format_pct(m['success_rate'])} | "
            f"{_format_pct(m['avg_file_recall'])} | "
            f"{_format_pct(m['avg_file_precision'])} | "
            f"{_format_pct(m['avg_line_coverage'])} | "
            f"{_format_pct(m['avg_line_precision_matched'])} | "
            f"{m['avg_turns']:.1f} | "
            f"{m['avg_latency_ms']:.0f}ms |"
        )

    return "\n".join(lines)


def _generate_markdown_grid_best(grid_path: Path, metric: str) -> str:
    runs = _load_grid_report(grid_path)
    best = _find_best_from_grid(runs, metric)

    if not best:
        return f"No runs found in {grid_path}"

    config = best.get("config", {})
    metrics = best.get("metrics", {})

    lines = [
        f"# Best Configuration from {grid_path.name}",
        "",
        f"**Optimized for**: `{metric}`",
        "",
        "## Configuration",
        f"- `search_max_turns`: {config.get('search_max_turns')}",
        f"- `search_temperature`: {config.get('search_temperature')}",
        "",
        "## Metrics",
        f"- Success Rate: {_format_pct(metrics.get('success_rate', 0))}",
        f"- File Recall: {_format_pct(metrics.get('avg_file_recall', 0))}",
        f"- File Precision: {_format_pct(metrics.get('avg_file_precision', 0))}",
        f"- Line Coverage: {_format_pct(metrics.get('avg_line_coverage', 0))}",
        f"- Line Prec (Matched): {_format_pct(metrics.get('avg_line_precision_matched', 0))}",
        f"- Avg Turns: {metrics.get('avg_turns', 0):.1f}",
        f"- Avg Latency: {metrics.get('avg_latency_ms', 0):.0f}ms",
    ]

    return "\n".join(lines)


@click.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output file (default: stdout). Use .md for Markdown, .json for JSON.",
)
@click.option(
    "--best",
    is_flag=True,
    help="Find best configuration from grid report (input must be .grid.json)",
)
@click.option(
    "--metric",
    default="avg_file_recall",
    show_default=True,
    help="Metric to optimize when using --best",
)
def main(inputs: tuple[str, ...], output: str | None, best: bool, metric: str) -> None:
    """Generate comparison reports from benchmark results.

    INPUTS: One or more .report.json or .grid.json files.

    Examples:

      # Compare multiple runs
      python -m benchmark.cli.report run1.report.json run2.report.json

      # Find best config from grid search
      python -m benchmark.cli.report --best grid_*.grid.json

      # Output to file
      python -m benchmark.cli.report -o comparison.md *.report.json
    """
    reports_dir = get_reports_dir()
    input_paths = []

    for inp in inputs:
        p = Path(inp)
        if not p.is_absolute():
            p = reports_dir / inp
        if not p.exists():
            click.echo(f"Warning: File not found: {p}", err=True)
            continue
        input_paths.append(p)

    if not input_paths:
        click.echo("Error: No valid input files found.", err=True)
        raise SystemExit(1)

    if best:
        if len(input_paths) != 1:
            click.echo("Error: --best requires exactly one .grid.json file.", err=True)
            raise SystemExit(1)
        content = _generate_markdown_grid_best(input_paths[0], metric)
    else:
        reports = []
        for p in input_paths:
            try:
                data = _load_report(p)
                reports.append((p.stem, data))
            except Exception as e:
                click.echo(f"Warning: Failed to load {p}: {e}", err=True)

        if not reports:
            click.echo("Error: No valid reports loaded.", err=True)
            raise SystemExit(1)

        content = _generate_markdown_comparison(reports)

    if output:
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = reports_dir / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content + "\n", encoding="utf-8")
        click.echo(f"Report saved to: {out_path}")
    else:
        click.echo(content)


if __name__ == "__main__":
    main()
