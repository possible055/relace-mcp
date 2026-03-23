import json
from pathlib import Path

import click

from ..analysis.search_map import (
    extract_batch,
    format_search_map_report,
)
from ..analysis.search_map_bundle import build_search_map_bundle
from ..analysis.trace_analyzer import aggregate_summary, analyze_batch, format_report
from ..analysis.trace_artifacts import (
    collect_trace_artifacts,
    format_trace_validation_report,
    validate_trace_run,
)
from ..config.paths import get_experiments_dir
from ..runner.experiment_paths import (
    experiment_reports_dir,
    find_latest_traces_dir,
    infer_experiment_root_from_traces,
)


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

    TRACES_PATH: Experiment root or directory containing trace artifacts.
    If not provided, uses --latest to find the most recent run.
    """
    if search_map and validate_artifacts:
        click.echo("Error: --search-map and --validate are mutually exclusive.", err=True)
        raise SystemExit(1)

    experiments_dir = get_experiments_dir()
    if traces_path:
        traces_dir = Path(traces_path)
        if not traces_dir.is_absolute():
            candidate = experiments_dir / traces_path
            traces_dir = candidate
        if traces_dir.is_dir() and (traces_dir / "traces").is_dir():
            traces_dir = traces_dir / "traces"
    elif latest:
        traces_dir = find_latest_traces_dir(experiments_dir)
        if traces_dir is None:
            click.echo(f"Error: No trace runs found under: {experiments_dir}", err=True)
            raise SystemExit(1)
        click.echo(f"Using latest trace run: {traces_dir.parent.name}")
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
        if json_out:
            bundle = build_search_map_bundle(traces_dir)
            content = json.dumps(bundle, indent=2, ensure_ascii=False)
        else:
            maps = extract_batch(traces_dir)
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
            experiment_root = infer_experiment_root_from_traces(traces_dir)
            if experiment_root is not None:
                out_path = experiment_reports_dir(experiment_root) / output
            else:
                out_path = traces_dir / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content + "\n", encoding="utf-8")
        click.echo(f"Report saved to: {out_path}")
    else:
        click.echo("")
        click.echo(content)


if __name__ == "__main__":
    main()
