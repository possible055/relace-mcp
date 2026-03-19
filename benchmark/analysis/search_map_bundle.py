import json
from pathlib import Path
from typing import Any

from ..runner.experiment_paths import (
    experiment_report_path,
    experiment_reports_dir,
    experiment_results_path,
    infer_experiment_root_from_traces,
)
from ..schemas import DatasetCase
from .search_map import SearchMap, aggregate_search_maps, extract_search_map
from .trace_artifacts import collect_trace_artifacts, load_trace_meta, load_trace_turns

SEARCH_MAP_BUNDLE_SCHEMA_VERSION = "1.0"
SEARCH_MAP_BUNDLE_FILENAME = "search_map.bundle.json"


def search_map_bundle_path(experiment_root: Path) -> Path:
    return experiment_reports_dir(experiment_root) / SEARCH_MAP_BUNDLE_FILENAME


def _load_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_results_by_case(results_path: Path | None) -> dict[str, dict[str, Any]]:
    if results_path is None or not results_path.exists():
        return {}

    results: dict[str, dict[str, Any]] = {}
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                continue
            case_id = data.get("case_id")
            if isinstance(case_id, str) and case_id:
                results[case_id] = data
    return results


def _load_dataset_cases(dataset_path: Path | None) -> dict[str, DatasetCase]:
    if dataset_path is None or not dataset_path.exists():
        return {}

    cases: dict[str, DatasetCase] = {}
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            case = DatasetCase.from_dict(raw)
            if case.id:
                cases[case.id] = case
    return cases


def _normalize_ranges(raw_ranges: Any) -> list[list[int]]:
    ranges: list[list[int]] = []
    if not isinstance(raw_ranges, list):
        return ranges
    for value in raw_ranges:
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and isinstance(value[0], int)
            and isinstance(value[1], int)
            and value[0] > 0
            and value[1] >= value[0]
        ):
            ranges.append([value[0], value[1]])
    return ranges


def _normalize_ground_truth_files(raw_files: dict[str, Any]) -> dict[str, list[list[int]]]:
    payload: dict[str, list[list[int]]] = {}
    for path, ranges in raw_files.items():
        if isinstance(path, str) and path:
            normalized = _normalize_ranges(ranges)
            if normalized:
                payload[path] = normalized
    return payload


def _normalize_ground_truth_functions(raw_functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for item in raw_functions:
        if not isinstance(item, dict):
            continue
        ranges = _normalize_ranges(item.get("ranges"))
        functions.append(
            {
                "path": item.get("path"),
                "name": item.get("name"),
                "container": item.get("container"),
                "start_line": item.get("start_line"),
                "ranges": ranges,
            }
        )
    return functions


def _merge_ranges(ranges: list[list[int]]) -> list[list[int]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda item: (item[0], item[1]))
    merged: list[list[int]] = [ordered[0][:]]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1] + 1:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged


def _is_file_path(path: str) -> bool:
    return bool(path) and path != "." and not path.endswith("/")


def _function_key(function: dict[str, Any]) -> tuple[str, str | None, str, tuple[int, int]]:
    raw_range = function.get("range") or [0, 0]
    if (
        isinstance(raw_range, list)
        and len(raw_range) >= 2
        and isinstance(raw_range[0], int)
        and isinstance(raw_range[1], int)
    ):
        range_key = (raw_range[0], raw_range[1])
    else:
        range_key = (0, 0)
    class_name = function.get("class")
    return (
        str(function.get("path", "")),
        class_name if isinstance(class_name, str) else None,
        str(function.get("function", "")),
        range_key,
    )


def _serialize_functions(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str | None, str, tuple[int, int]], dict[str, Any]] = {}
    for function in functions:
        key = _function_key(function)
        unique.setdefault(key, function)
    return sorted(
        [dict(item) for item in unique.values()],
        key=lambda item: (
            str(item.get("path", "")),
            int((item.get("range") or [0, 0])[0]),
            str(item.get("class") or ""),
            str(item.get("function") or ""),
        ),
    )


def _build_file_blocks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], dict[str, Any]] = {}
    for event in events:
        path = event.get("path")
        if not isinstance(path, str) or not _is_file_path(path):
            continue
        turn = event.get("turn")
        block_kind = event.get("access_type")
        if not isinstance(turn, int) or not isinstance(block_kind, str):
            continue
        group = grouped.setdefault(
            (path, block_kind, turn),
            {
                "path": path,
                "block_kind": block_kind,
                "ranges": [],
                "first_turn": turn,
                "last_turn": turn,
                "event_count": 0,
                "source_tools": set(),
                "symbols": set(),
                "functions": [],
            },
        )
        group["event_count"] += 1
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            group["source_tools"].add(tool_name)
        lines = event.get("lines")
        if (
            isinstance(lines, list)
            and len(lines) >= 2
            and isinstance(lines[0], int)
            and isinstance(lines[1], int)
        ):
            group["ranges"].append([lines[0], lines[1]])
        symbol_name = event.get("symbol_name")
        symbol_kind = event.get("symbol_kind")
        if isinstance(symbol_name, str) and symbol_name:
            if isinstance(symbol_kind, str) and symbol_kind:
                group["symbols"].add(f"{symbol_kind}:{symbol_name}")
            else:
                group["symbols"].add(symbol_name)
        group["functions"].extend(event.get("functions", []))

    blocks: list[dict[str, Any]] = []
    for (_, _, _), group in sorted(grouped.items(), key=lambda item: item[0]):
        symbols = sorted(group["symbols"])
        blocks.append(
            {
                "path": group["path"],
                "block_kind": group["block_kind"],
                "ranges": _merge_ranges(group["ranges"]),
                "first_turn": group["first_turn"],
                "last_turn": group["last_turn"],
                "event_count": group["event_count"],
                "source_tools": sorted(group["source_tools"]),
                "symbols": symbols,
                "functions": _serialize_functions(group["functions"]),
            }
        )
    return blocks


def _build_function_blocks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str | None, str, tuple[int, int]], dict[str, Any]] = {}
    for event in events:
        turn = event.get("turn")
        if not isinstance(turn, int):
            continue
        for function in event.get("functions", []):
            key = _function_key(function)
            group = grouped.setdefault(
                key,
                {
                    "path": function.get("path"),
                    "function": function.get("function"),
                    "class": function.get("class"),
                    "range": function.get("range"),
                    "signature": function.get("signature"),
                    "first_turn": turn,
                    "last_turn": turn,
                    "access_kinds": set(),
                    "source_tools": set(),
                },
            )
            group["first_turn"] = min(group["first_turn"], turn)
            group["last_turn"] = max(group["last_turn"], turn)
            access_type = event.get("access_type")
            if isinstance(access_type, str) and access_type:
                group["access_kinds"].add(access_type)
            tool_name = event.get("tool_name")
            if isinstance(tool_name, str) and tool_name:
                group["source_tools"].add(tool_name)

    blocks: list[dict[str, Any]] = []
    for _, group in sorted(grouped.items(), key=lambda item: item[0]):
        blocks.append(
            {
                "path": group["path"],
                "function": group["function"],
                "class": group["class"],
                "range": group["range"],
                "signature": group["signature"],
                "first_turn": group["first_turn"],
                "last_turn": group["last_turn"],
                "access_kinds": sorted(group["access_kinds"]),
                "source_tools": sorted(group["source_tools"]),
            }
        )
    return blocks


def _build_turn_summaries(
    turns: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    events_by_turn: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        turn = event.get("turn")
        if isinstance(turn, int):
            events_by_turn.setdefault(turn, []).append(event)

    seen_files: set[str] = set()
    seen_functions: set[tuple[str, str | None, str, tuple[int, int]]] = set()
    summaries: list[dict[str, Any]] = []
    for index, entry in enumerate(turns, 1):
        turn = entry.get("turn")
        if not isinstance(turn, int) or turn <= 0:
            turn = index
        turn_events = events_by_turn.get(turn, [])

        new_files: list[str] = []
        for event in turn_events:
            path = event.get("path")
            if isinstance(path, str) and _is_file_path(path) and path not in seen_files:
                seen_files.add(path)
                new_files.append(path)

        new_functions: list[dict[str, Any]] = []
        for event in turn_events:
            for function in event.get("functions", []):
                key = _function_key(function)
                if key in seen_functions:
                    continue
                seen_functions.add(key)
                new_functions.append(function)

        usage = (entry.get("llm_response") or {}).get("usage") or {}
        tool_results = entry.get("tool_results", [])
        tool_names = [
            item.get("name")
            for item in tool_results
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        selected_files = sorted(
            {
                event["path"]
                for event in turn_events
                if event.get("access_type") == "select" and isinstance(event.get("path"), str)
            }
        )
        summaries.append(
            {
                "turn": turn,
                "tool_count": len(tool_names),
                "tool_names": tool_names,
                "new_files": sorted(new_files),
                "new_functions": _serialize_functions(new_functions),
                "selected_files": selected_files,
                "llm_latency_ms": entry.get("llm_latency_ms"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            }
        )
    return summaries


def _result_status(result: dict[str, Any] | None) -> str:
    if result is None:
        return "missing_result"
    if bool(result.get("partial", False)):
        return "partial"
    if isinstance(result.get("error"), str) and result.get("error"):
        return "error"
    return "ok"


def _build_metrics_snapshot(result: dict[str, Any] | None) -> dict[str, Any]:
    if result is None:
        return {"result_status": "missing_result"}
    keys = [
        "completed",
        "partial",
        "error",
        "turns_used",
        "latency_s",
        "file_recall",
        "file_precision",
        "line_coverage",
        "line_precision_matched",
        "context_line_coverage",
        "context_line_precision_matched",
        "function_hit_rate",
        "functions_hit",
        "functions_total",
        "returned_files_count",
        "search_mode",
        "hints_used",
        "retrieval_backend",
        "retrieval_latency_s",
        "reindex_action",
    ]
    snapshot = {key: result.get(key) for key in keys}
    snapshot["result_status"] = _result_status(result)
    return snapshot


def _build_case_payload(
    *,
    search_map: SearchMap,
    turns: list[dict[str, Any]],
    meta: dict[str, Any],
    result: dict[str, Any] | None,
    dataset_case: DatasetCase | None,
) -> dict[str, Any]:
    events = [event.to_dict() for event in search_map.events]

    query = ""
    repo = meta.get("repo") if isinstance(meta.get("repo"), str) else None
    base_commit = None
    ground_truth_files: dict[str, list[list[int]]] = {}
    ground_truth_context_files: dict[str, list[list[int]]] = {}
    ground_truth_functions: list[dict[str, Any]] = []
    if dataset_case is not None:
        query = dataset_case.query
        repo = dataset_case.repo or repo
        base_commit = dataset_case.base_commit
        ground_truth_files = _normalize_ground_truth_files(dataset_case.ground_truth_files)
        ground_truth_context_files = _normalize_ground_truth_files(
            dataset_case.ground_truth_context_files
        )
        ground_truth_functions = _normalize_ground_truth_functions(
            dataset_case.ground_truth_functions
        )
    elif isinstance(meta.get("query"), str):
        query = meta.get("query", "")

    return {
        "case_id": search_map.case_id,
        "query": query,
        "repo": repo,
        "base_commit": base_commit,
        "semantic_hints": search_map.semantic_hints,
        "ground_truth_files": ground_truth_files,
        "ground_truth_context_files": ground_truth_context_files,
        "ground_truth_functions": ground_truth_functions,
        "events": events,
        "turn_summaries": _build_turn_summaries(turns, events),
        "file_blocks": _build_file_blocks(events),
        "function_blocks": _build_function_blocks(events),
        "selected_files": sorted(search_map.selected_files),
        "unique_files": sorted(search_map.unique_files),
        "unique_functions": search_map.unique_functions,
        "metrics_snapshot": _build_metrics_snapshot(result),
        "result_status": _result_status(result),
    }


def _build_experiment_payload(
    *,
    metadata: dict[str, Any],
    experiment_root: Path | None,
    traces_dir: Path,
    report_path: Path | None,
    results_path: Path | None,
) -> dict[str, Any]:
    experiment = metadata.get("experiment") if isinstance(metadata.get("experiment"), dict) else {}
    run = metadata.get("run") if isinstance(metadata.get("run"), dict) else {}
    search = metadata.get("search") if isinstance(metadata.get("search"), dict) else {}
    retrieval = metadata.get("retrieval") if isinstance(metadata.get("retrieval"), dict) else {}
    dataset = metadata.get("dataset") if isinstance(metadata.get("dataset"), dict) else {}

    root_str = str(experiment_root) if experiment_root is not None else None
    return {
        "name": experiment.get("name")
        or (experiment_root.name if experiment_root is not None else None),
        "root": experiment.get("root") or root_str,
        "type": experiment.get("type"),
        "traces_dir": str(traces_dir),
        "report_path": str(report_path)
        if report_path is not None and report_path.exists()
        else None,
        "results_path": str(results_path)
        if results_path is not None and results_path.exists()
        else None,
        "run": run,
        "search": search,
        "retrieval": retrieval,
        "dataset": dataset,
    }


def build_search_map_bundle(traces_dir: Path) -> dict[str, Any]:
    artifacts = collect_trace_artifacts(traces_dir)
    experiment_root = infer_experiment_root_from_traces(traces_dir)
    report_path = experiment_report_path(experiment_root) if experiment_root is not None else None
    results_path = experiment_results_path(experiment_root) if experiment_root is not None else None

    report = _load_json(report_path)
    metadata = report.get("metadata", {}) if isinstance(report, dict) else {}
    dataset_path_raw = None
    if isinstance(metadata, dict):
        dataset = metadata.get("dataset")
        if isinstance(dataset, dict):
            dataset_path_raw = dataset.get("dataset_path")
    dataset_path = (
        Path(dataset_path_raw) if isinstance(dataset_path_raw, str) and dataset_path_raw else None
    )

    results_by_case = _load_results_by_case(results_path)
    dataset_cases = _load_dataset_cases(dataset_path)

    cases: list[dict[str, Any]] = []
    maps: list[SearchMap] = []
    for artifact in artifacts:
        search_map = extract_search_map(
            artifact.trace_path,
            artifact.case_id,
            meta_path=artifact.meta_path,
        )
        maps.append(search_map)
        turns, _ = load_trace_turns(artifact.trace_path)
        meta, _ = load_trace_meta(artifact.meta_path)
        cases.append(
            _build_case_payload(
                search_map=search_map,
                turns=turns,
                meta=meta,
                result=results_by_case.get(artifact.case_id),
                dataset_case=dataset_cases.get(artifact.case_id),
            )
        )

    summary = aggregate_search_maps(maps)
    summary["cases_with_dataset_context"] = sum(1 for case in cases if case.get("query"))

    return {
        "schema_version": SEARCH_MAP_BUNDLE_SCHEMA_VERSION,
        "kind": "search_map_bundle",
        "experiment": _build_experiment_payload(
            metadata=metadata if isinstance(metadata, dict) else {},
            experiment_root=experiment_root,
            traces_dir=traces_dir,
            report_path=report_path,
            results_path=results_path,
        ),
        "summary": summary,
        "cases": cases,
    }


def build_search_map_bundle_from_experiment(experiment_root: Path) -> dict[str, Any]:
    return build_search_map_bundle(experiment_root / "traces")


def load_search_map_bundle(experiment_root: Path) -> dict[str, Any]:
    bundle_path = search_map_bundle_path(experiment_root)
    existing = _load_json(bundle_path)
    if isinstance(existing, dict) and existing.get("kind") == "search_map_bundle":
        return existing
    return build_search_map_bundle_from_experiment(experiment_root)
