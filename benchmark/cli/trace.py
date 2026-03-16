import json
from pathlib import Path

import click

from ..analysis.search_map import (
    aggregate_search_maps,
    extract_batch,
    format_search_map_report,
)
from ..analysis.trace_analyzer import aggregate_summary, analyze_batch, format_report
from ..analysis.trace_artifacts import (
    collect_trace_artifacts,
    format_trace_validation_report,
    validate_trace_run,
)
from ..config import ARTIFACTS_DIR

TRACES_DIR = ARTIFACTS_DIR / "traces"


@click.command()
@click.argument("traces_path", required=False, default=None)
@click.option(
    "-o",
    "--output",
    default=None,
    help="Save report to file (supports .md and .json)",
)
@click.option("--json-out", is_flag=True, help="Output raw JSON summary instead of text report")
@click.option("--latest", is_flag=True, help="Analyze the latest trace run")
@click.option(
    "--search-map", is_flag=True, help="Generate search map analysis instead of behavioral report"
)
@click.option("--validate", "validate_artifacts", is_flag=True, help="Validate trace artifacts")
def main(
    traces_path: str | None,
    output: str | None,
    json_out: bool,
    latest: bool,
    search_map: bool,
    validate_artifacts: bool,
) -> None:
    """Analyze benchmark trace data for behavioral patterns.

    TRACES_PATH: Directory containing .jsonl trace files.
    If not provided, uses --latest to find the most recent run.
    """
    if search_map and validate_artifacts:
        click.echo("Error: --search-map and --validate are mutually exclusive.", err=True)
        raise SystemExit(1)

    if traces_path:
        traces_dir = Path(traces_path)
        if not traces_dir.is_absolute():
            traces_dir = TRACES_DIR / traces_path
    elif latest:
        if not TRACES_DIR.exists():
            click.echo(f"Error: Traces directory not found: {TRACES_DIR}", err=True)
            raise SystemExit(1)
        subdirs = sorted(
            [d for d in TRACES_DIR.iterdir() if d.is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )
        if not subdirs:
            click.echo("Error: No trace runs found.", err=True)
            raise SystemExit(1)
        traces_dir = subdirs[0]
        click.echo(f"Using latest trace run: {traces_dir.name}")
    else:
        click.echo("Error: Provide TRACES_PATH or use --latest.", err=True)
        raise SystemExit(1)

    if not traces_dir.exists():
        click.echo(f"Error: Directory not found: {traces_dir}", err=True)
        raise SystemExit(1)

    trace_artifacts = collect_trace_artifacts(traces_dir)
    trace_files = list(traces_dir.glob("*.jsonl"))

    if validate_artifacts:
        if not trace_artifacts:
            click.echo(f"Error: No trace artifacts found in {traces_dir}", err=True)
            raise SystemExit(1)
        click.echo(f"Validating {len(trace_artifacts)} trace artifact sets from: {traces_dir}")
        summary = validate_trace_run(traces_dir)
        content = (
            json.dumps(summary.to_dict(), indent=2, ensure_ascii=False)
            if json_out
            else format_trace_validation_report(summary)
        )
    elif search_map:
        if not trace_artifacts:
            click.echo(f"Error: No trace artifacts found in {traces_dir}", err=True)
            raise SystemExit(1)
        click.echo(f"Analyzing {len(trace_artifacts)} trace artifact sets from: {traces_dir}")
        maps = extract_batch(traces_dir)
        if json_out:
            summary = aggregate_search_maps(maps)
            per_case = [m.to_dict() for m in maps]
            summary["per_case"] = per_case
            content = json.dumps(summary, indent=2, ensure_ascii=False)
        else:
            content = format_search_map_report(maps)
    else:
        if not trace_files:
            click.echo(f"Error: No .jsonl trace files found in {traces_dir}", err=True)
            raise SystemExit(1)
        click.echo(f"Analyzing {len(trace_files)} trace files from: {traces_dir}")
        analyses = analyze_batch(traces_dir)
        if json_out:
            summary = aggregate_summary(analyses)
            content = json.dumps(summary, indent=2, ensure_ascii=False)
        else:
            content = format_report(analyses)

    if output:
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = traces_dir / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content + "\n", encoding="utf-8")
        click.echo(f"Report saved to: {out_path}")
    else:
        click.echo("")
        click.echo(content)


if __name__ == "__main__":
    main()
