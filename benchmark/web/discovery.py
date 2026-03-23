import json
from pathlib import Path
from typing import Any

from benchmark.analysis.search_map_bundle import SEARCH_MAP_BUNDLE_FILENAME

REPORT_FILENAME = "summary.report.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _experiment_from_report(path: Path) -> Path:
    return path.parent.parent


def _report_metadata(
    report: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return {}, {}, {}
    experiment = metadata.get("experiment")
    search = metadata.get("search")
    run = metadata.get("run")
    return (
        experiment if isinstance(experiment, dict) else {},
        search if isinstance(search, dict) else {},
        run if isinstance(run, dict) else {},
    )


def _bundle_case_count(experiment_root: Path) -> int | None:
    bundle_path = experiment_root / "reports" / SEARCH_MAP_BUNDLE_FILENAME
    if not bundle_path.exists():
        return None
    try:
        payload = _load_json(bundle_path)
    except Exception:
        return None
    cases = payload.get("cases")
    return len(cases) if isinstance(cases, list) else None


def _summary_from_report(report_path: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    experiment_meta, search_meta, run_meta = _report_metadata(report)
    experiment_root = _experiment_from_report(report_path)
    summary: dict[str, Any] = {
        "name": experiment_meta.get("name") or experiment_root.name,
        "root": str(experiment_root),
        "type": experiment_meta.get("type") or "unknown",
        "provider": search_meta.get("provider"),
        "model": search_meta.get("model"),
        "search_mode": run_meta.get("search_mode"),
        "max_turns": search_meta.get("max_turns"),
        "temperature": search_meta.get("temperature"),
        "has_bundle": (experiment_root / "reports" / SEARCH_MAP_BUNDLE_FILENAME).exists(),
        "case_count": _bundle_case_count(experiment_root),
    }
    if summary["case_count"] is None:
        cases_loaded = run_meta.get("cases_loaded")
        if isinstance(cases_loaded, int):
            summary["case_count"] = cases_loaded
    return summary


def list_experiments(experiments_root: Path) -> list[dict[str, Any]]:
    if not experiments_root.exists():
        return []

    summaries: dict[str, dict[str, Any]] = {}

    for report_path in sorted(experiments_root.rglob(REPORT_FILENAME)):
        experiment_root = _experiment_from_report(report_path)
        try:
            summaries[str(experiment_root.resolve())] = _summary_from_report(report_path)
        except Exception:
            continue

    for bundle_path in sorted(experiments_root.rglob(SEARCH_MAP_BUNDLE_FILENAME)):
        experiment_root = bundle_path.parent.parent
        key = str(experiment_root.resolve())
        if key in summaries:
            summaries[key]["has_bundle"] = True
            if summaries[key].get("case_count") is None:
                summaries[key]["case_count"] = _bundle_case_count(experiment_root)
            continue
        summaries[key] = {
            "name": experiment_root.name,
            "root": str(experiment_root),
            "type": "unknown",
            "provider": None,
            "model": None,
            "search_mode": None,
            "max_turns": None,
            "temperature": None,
            "has_bundle": True,
            "case_count": _bundle_case_count(experiment_root),
        }

    return sorted(
        summaries.values(),
        key=lambda item: (
            str(item.get("type") or ""),
            str(item.get("name") or ""),
            str(item.get("root") or ""),
        ),
    )
