import json
from collections import Counter
from pathlib import Path

import click

from ..config import get_reports_dir, get_results_dir


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl_results(path: Path) -> list[dict]:
    results = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                results.append(json.loads(stripped))
    return results


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


def _generate_failures_report(results_path: Path) -> str:
    results = _load_jsonl_results(results_path)
    total = len(results)
    partial_cases = [r for r in results if r.get("partial", False)]
    failed_cases = [r for r in results if not r.get("success", True)]

    lines = [
        f"# Failure Analysis: {results_path.name}",
        "",
        f"**Total Cases**: {total}",
        f"**Failed (success=false)**: {len(failed_cases)} ({len(failed_cases) / total * 100:.1f}%)",
        f"**Incomplete (partial=true)**: {len(partial_cases)} ({len(partial_cases) / total * 100:.1f}%)",
        "",
    ]

    # Error type breakdown
    error_counts: Counter[str] = Counter()
    for r in failed_cases:
        error = r.get("error") or "no_report_back"
        if "timeout" in error.lower():
            error_counts["timeout"] += 1
        elif "rate limit" in error.lower():
            error_counts["rate_limit"] += 1
        elif "api" in error.lower():
            error_counts["api_error"] += 1
        elif error == "no_report_back":
            error_counts["no_report_back"] += 1
        else:
            error_counts["other"] += 1

    if error_counts:
        lines.append("## Error Types")
        for error_type, count in error_counts.most_common():
            lines.append(f"- `{error_type}`: {count}")
        lines.append("")

    # List incomplete cases
    if partial_cases:
        lines.append("## Incomplete Cases (no report_back)")
        lines.append("")
        lines.append("| Case ID | Repo | Turns | Error |")
        lines.append("|---------|------|-------|-------|")
        for r in partial_cases[:20]:
            case_id = r.get("case_id", "")[:30]
            repo = r.get("repo", "")[:25]
            turns = r.get("turns_used", 0)
            error = (r.get("error") or "reached max turns")[:40]
            lines.append(f"| {case_id} | {repo} | {turns} | {error} |")
        if len(partial_cases) > 20:
            lines.append(f"| ... | ... | ... | ({len(partial_cases) - 20} more) |")

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
    "--failures",
    is_flag=True,
    help="Analyze failed/incomplete cases from .jsonl result files",
)
@click.option(
    "--metric",
    default="avg_file_recall",
    show_default=True,
    help="Metric to optimize when using --best",
)
def main(
    inputs: tuple[str, ...], output: str | None, best: bool, failures: bool, metric: str
) -> None:
    """Generate comparison reports from benchmark results.

    INPUTS: One or more .report.json, .grid.json, or .jsonl files.

    Examples:

      # Compare multiple runs
      python -m benchmark.cli.report run1.report.json run2.report.json

      # Find best config from grid search
      python -m benchmark.cli.report --best grid_*.grid.json

      # Analyze failures from result file
      python -m benchmark.cli.report --failures run.jsonl

      # Output to file
      python -m benchmark.cli.report -o comparison.md *.report.json
    """
    reports_dir = get_reports_dir()
    results_dir = get_results_dir()
    input_paths = []

    for inp in inputs:
        p = Path(inp)
        if not p.is_absolute():
            # Try reports dir first, then results dir
            if (reports_dir / inp).exists():
                p = reports_dir / inp
            elif (results_dir / inp).exists():
                p = results_dir / inp
            else:
                p = Path(inp)
        if not p.exists():
            click.echo(f"Warning: File not found: {p}", err=True)
            continue
        input_paths.append(p)

    if not input_paths:
        click.echo("Error: No valid input files found.", err=True)
        raise SystemExit(1)

    if failures:
        if len(input_paths) != 1:
            click.echo("Error: --failures requires exactly one .jsonl file.", err=True)
            raise SystemExit(1)
        content = _generate_failures_report(input_paths[0])
    elif best:
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
