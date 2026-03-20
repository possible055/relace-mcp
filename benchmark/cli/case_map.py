import json
from pathlib import Path
from typing import Any

import click

from ..analysis.case_map_compare import build_case_map_compare, format_case_map_compare_report
from ..analysis.search_map_bundle import SEARCH_MAP_BUNDLE_FILENAME
from ..config.paths import get_experiments_dir


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _experiment_type(report: dict[str, Any]) -> str | None:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return None
    experiment = metadata.get("experiment")
    if not isinstance(experiment, dict):
        return None
    value = experiment.get("type")
    return value if isinstance(value, str) else None


def _experiment_root_from_report(path: Path, report: dict[str, Any]) -> Path:
    metadata = report.get("metadata")
    if isinstance(metadata, dict):
        experiment = metadata.get("experiment")
        if isinstance(experiment, dict):
            root = experiment.get("root")
            if isinstance(root, str) and root:
                return Path(root)
    return path.parent.parent


def _grid_trial_roots_from_report(path: Path, report: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    grid = report.get("grid")
    if isinstance(grid, dict):
        for trial in grid.get("trials", []):
            if not isinstance(trial, dict):
                continue
            paths = trial.get("paths")
            if not isinstance(paths, dict):
                continue
            experiment_root = paths.get("experiment_root")
            if isinstance(experiment_root, str) and experiment_root:
                roots.append(Path(experiment_root))
    if roots:
        return roots

    root = _experiment_root_from_report(path, report)
    runs_dir = root / "runs"
    if runs_dir.is_dir():
        return sorted(
            [child for child in runs_dir.iterdir() if child.is_dir()], key=lambda p: str(p)
        )
    return []


def _expand_input_path(path: Path) -> list[Path]:
    if path.is_file():
        if path.name == SEARCH_MAP_BUNDLE_FILENAME:
            return [path.parent.parent]
        if path.name.endswith(".report.json"):
            report = _load_json(path)
            if isinstance(report, dict) and _experiment_type(report) == "grid":
                return _grid_trial_roots_from_report(path, report)
            return [_experiment_root_from_report(path, report if isinstance(report, dict) else {})]
        raise click.ClickException(f"Unsupported input file: {path}")

    if path.is_dir():
        if path.name == "traces":
            return [path.parent]
        bundle_path = path / "reports" / SEARCH_MAP_BUNDLE_FILENAME
        if bundle_path.exists():
            return [path]
        report_path = path / "reports" / "summary.report.json"
        if report_path.exists():
            report = _load_json(report_path)
            if isinstance(report, dict) and _experiment_type(report) == "grid":
                return _grid_trial_roots_from_report(report_path, report)
            return [path]
        runs_dir = path / "runs"
        if runs_dir.is_dir() and not (path / "traces").is_dir():
            return sorted(
                [child for child in runs_dir.iterdir() if child.is_dir()], key=lambda p: str(p)
            )
        if (path / "traces").is_dir():
            return [path]

    raise click.ClickException(f"Unsupported input path: {path}")


def _resolve_input_paths(inputs: tuple[str, ...]) -> list[Path]:
    experiments_dir = get_experiments_dir()
    roots: list[Path] = []
    seen: set[str] = set()

    for raw in inputs:
        path = Path(raw)
        if not path.is_absolute():
            candidate = experiments_dir / raw
            if candidate.exists():
                path = candidate
        if not path.exists():
            raise click.ClickException(f"Input not found: {path}")
        for root in _expand_input_path(path):
            resolved = str(root.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            roots.append(root)
    return roots


@click.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option("--case-id", required=True, help="Case ID to compare across runs.")
@click.option("--json-out", is_flag=True, help="Output raw compare JSON instead of Markdown.")
@click.option(
    "-o",
    "--output",
    default=None,
    help="Output file (default: stdout; relative paths write under benchmark/.data/experiments/_compare/).",
)
def main(inputs: tuple[str, ...], case_id: str, json_out: bool, output: str | None) -> None:
    """Compare a single benchmark case across multiple runs or grid trials."""
    experiment_roots = _resolve_input_paths(inputs)
    payload = build_case_map_compare(case_id, experiment_roots)

    if json_out:
        content = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        content = format_case_map_compare_report(payload)

    if output:
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = get_experiments_dir() / "_compare" / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content + "\n", encoding="utf-8")
        click.echo(f"Report saved to: {out_path}")
    else:
        click.echo(content)


if __name__ == "__main__":
    main()
