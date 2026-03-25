import json
from collections import Counter
from pathlib import Path

import click

from ..config.paths import get_experiments_dir


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


def _is_report_file(path: Path) -> bool:
    return path.name == "summary.json"


def _is_results_jsonl(path: Path) -> bool:
    return path.suffix == ".jsonl"


def _experiment_type(report: dict) -> str | None:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return None
    experiment = metadata.get("experiment")
    if not isinstance(experiment, dict):
        return None
    value = experiment.get("type")
    return value if isinstance(value, str) else None


def _experiment_name(report: dict) -> str | None:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return None
    experiment = metadata.get("experiment")
    if not isinstance(experiment, dict):
        return None
    value = experiment.get("name")
    return value if isinstance(value, str) else None


def _report_label(path: Path, report: dict) -> str:
    name = _experiment_name(report)
    if name:
        return name
    if path.name == "summary.json":
        return path.parent.name
    return path.stem


def _validate_mode_inputs(
    input_paths: list[Path],
    *,
    best: bool,
    failures: bool,
) -> None:
    if failures:
        if len(input_paths) != 1:
            raise click.ClickException("--failures requires exactly one .jsonl file.")
        if not _is_results_jsonl(input_paths[0]):
            raise click.ClickException("--failures only accepts a single .jsonl result file.")
        return

    if best:
        if len(input_paths) != 1:
            raise click.ClickException("--best requires exactly one grid summary.json file.")
        if not _is_report_file(input_paths[0]):
            raise click.ClickException("--best only accepts a single grid summary.json file.")
        return

    invalid_paths = [str(path) for path in input_paths if not _is_report_file(path)]
    if invalid_paths:
        invalid_display = ", ".join(invalid_paths)
        raise click.ClickException(
            "Comparison mode only accepts summary.json inputs. "
            "Use --best for grid summary.json or --failures for .jsonl. "
            f"Invalid inputs: {invalid_display}"
        )


def _extract_metrics(report: dict) -> dict:
    if _experiment_type(report) == "grid":
        return {}
    return {
        "completion_rate": report.get("completion_rate", 0),
        "avg_quality_score": report.get("avg_quality_score", 0),
        "avg_file_recall": report.get("avg_file_recall", 0),
        "avg_file_precision": report.get("avg_file_precision", 0),
        "avg_line_coverage": report.get("avg_line_coverage", 0),
        "avg_line_precision_matched": report.get("avg_line_precision_matched", 0),
        "avg_turns": report.get("avg_turns", 0),
        "avg_latency_s": report.get("avg_latency_s", 0),
    }


def _find_best_from_grid(runs: list[dict], metric: str = "avg_file_recall") -> dict | None:
    if not runs:
        return None
    best = max(runs, key=lambda r: r.get("metrics", {}).get(metric, 0) or 0)
    return best


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _generate_markdown_comparison(reports: list[tuple[str, dict]]) -> str:
    lines = ["# Benchmark Comparison Report", ""]

    lines.append("| Run | Compl. | Quality | F.Recall | F.Prec | L.Prec(M) | Turns | Latency |")
    lines.append("|-----|--------|---------|----------|--------|-----------|-------|---------|")

    for name, report in reports:
        m = _extract_metrics(report)
        if not m:
            continue
        lines.append(
            f"| {name} | "
            f"{_format_pct(m['completion_rate'])} | "
            f"{_format_pct(m['avg_quality_score'])} | "
            f"{_format_pct(m['avg_file_recall'])} | "
            f"{_format_pct(m['avg_file_precision'])} | "
            f"{_format_pct(m['avg_line_precision_matched'])} | "
            f"{m['avg_turns']:.1f} | "
            f"{m['avg_latency_s']:.1f}s |"
        )

    return "\n".join(lines)


def _generate_markdown_grid_best(grid_path: Path, metric: str) -> str:
    report = _load_report(grid_path)
    if _experiment_type(report) != "grid":
        raise click.ClickException("--best only accepts a single grid summary.json file.")

    grid_payload = report.get("grid")
    if not isinstance(grid_payload, dict):
        return f"No grid payload found in {grid_path}"

    runs = grid_payload.get("trials", [])
    if not isinstance(runs, list):
        return f"No grid trials found in {grid_path}"
    best = _find_best_from_grid(runs, metric)

    if not best:
        return f"No runs found in {grid_path}"

    config = best.get("config", {})
    metrics = best.get("metrics", {})

    title_name = _report_label(grid_path, report)
    lines = [
        f"# Best Configuration from {title_name}",
        "",
        f"**Optimized for**: `{metric}`",
        "",
        "## Configuration",
        f"- `search_max_turns`: {config.get('search_max_turns')}",
        f"- `search_temperature`: {config.get('search_temperature')}",
        "",
        "## Metrics",
        f"- Completion Rate: {_format_pct(metrics.get('completion_rate', 0))}",
        f"- Quality Score: {_format_pct(metrics.get('avg_quality_score', 0))}",
        f"- File Recall: {_format_pct(metrics.get('avg_file_recall', 0))}",
        f"- File Precision: {_format_pct(metrics.get('avg_file_precision', 0))}",
        f"- Line Prec (Matched): {_format_pct(metrics.get('avg_line_precision_matched', 0))}",
        f"- Avg Turns: {metrics.get('avg_turns', 0):.1f}",
        f"- Avg Latency: {metrics.get('avg_latency_s', 0):.1f}s",
        f"- Experiment Root: {best.get('paths', {}).get('experiment_root')}",
    ]

    return "\n".join(lines)


def _generate_failures_report(results_path: Path) -> str:
    results = _load_jsonl_results(results_path)
    total = len(results)
    partial_cases = [r for r in results if r.get("partial", False)]
    incomplete_cases = [r for r in results if not r.get("completed", True)]

    incomplete_pct = (len(incomplete_cases) / total * 100) if total else 0.0
    partial_pct = (len(partial_cases) / total * 100) if total else 0.0

    lines = [
        f"# Failure Analysis: {results_path.name}",
        "",
        f"**Total Cases**: {total}",
        f"**Incomplete (completed=false)**: {len(incomplete_cases)} ({incomplete_pct:.1f}%)",
        f"**Partial (partial=true)**: {len(partial_cases)} ({partial_pct:.1f}%)",
        "",
    ]

    # Error type breakdown
    error_counts: Counter[str] = Counter()
    for r in incomplete_cases:
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
    help="Output file (default: stdout). Writes plain text / Markdown content.",
)
@click.option(
    "--best",
    is_flag=True,
    help="Find best configuration from a grid summary.json file",
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

    INPUTS: Accepted formats depend on mode.

    Examples:

      # Compare multiple runs
      python -m benchmark.cli.report run1/summary.json run2/summary.json

      # Find best config from grid search
      python -m benchmark.cli.report --best path/to/grid/summary.json

      # Analyze failures from result file
      python -m benchmark.cli.report --failures run.jsonl

      # Output to file
      python -m benchmark.cli.report -o comparison.md */summary.json
    """
    experiments_dir = get_experiments_dir()
    input_paths = []

    for inp in inputs:
        p = Path(inp)
        if not p.is_absolute():
            if (experiments_dir / inp).exists():
                p = experiments_dir / inp
            else:
                matches = sorted(experiments_dir.rglob(inp)) if experiments_dir.exists() else []
                p = matches[0] if len(matches) == 1 else Path(inp)
        if not p.exists():
            click.echo(f"Warning: File not found: {p}", err=True)
            continue
        input_paths.append(p)

    if not input_paths:
        click.echo("Error: No valid input files found.", err=True)
        raise SystemExit(1)

    _validate_mode_inputs(input_paths, best=best, failures=failures)

    if failures:
        content = _generate_failures_report(input_paths[0])
    elif best:
        content = _generate_markdown_grid_best(input_paths[0], metric)
    else:
        reports = []
        for p in input_paths:
            try:
                data = _load_report(p)
                if _experiment_type(data) == "grid":
                    raise click.ClickException(
                        "Comparison mode does not accept grid parent reports. Use --best instead."
                    )
                reports.append((_report_label(p, data), data))
            except click.ClickException:
                raise
            except Exception as e:
                click.echo(f"Warning: Failed to load {p}: {e}", err=True)

        if not reports:
            click.echo("Error: No valid reports loaded.", err=True)
            raise SystemExit(1)

        content = _generate_markdown_comparison(reports)

    if output:
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = experiments_dir / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content + "\n", encoding="utf-8")
        click.echo(f"Report saved to: {out_path}")
    else:
        click.echo(content)


if __name__ == "__main__":
    main()
