from pathlib import Path
from typing import Any

from .search_map_bundle import load_search_map_bundle

CASE_MAP_COMPARE_SCHEMA_VERSION = "1.0"


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


def _serialize_function(function: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": function.get("path"),
        "function": function.get("function"),
        "class": function.get("class"),
        "range": function.get("range"),
        "signature": function.get("signature"),
    }


def _search_config(bundle: dict[str, Any]) -> dict[str, Any]:
    experiment = bundle.get("experiment", {})
    search = experiment.get("search", {}) if isinstance(experiment, dict) else {}
    run = experiment.get("run", {}) if isinstance(experiment, dict) else {}
    return {
        "provider": search.get("provider"),
        "model": search.get("model"),
        "search_mode": run.get("search_mode"),
        "max_turns": search.get("max_turns"),
        "temperature": search.get("temperature"),
        "prompt_file": search.get("prompt_file"),
    }


def _run_label(bundle: dict[str, Any]) -> str:
    experiment = bundle.get("experiment", {})
    config = _search_config(bundle)
    name = experiment.get("name") if isinstance(experiment, dict) else None
    provider = config.get("provider") or "unknown"
    model = config.get("model") or "unknown"
    search_mode = config.get("search_mode") or "unknown"
    max_turns = config.get("max_turns")
    temperature = config.get("temperature")
    return (
        f"{name or 'unknown'} | {provider}/{model} | mode={search_mode} | "
        f"turns={max_turns} | temp={temperature}"
    )


def _case_index(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = bundle.get("cases", [])
    if not isinstance(cases, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if isinstance(case_id, str) and case_id:
            result[case_id] = case
    return result


def _path_status(case_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    hinted_paths = {
        item.get("filename")
        for item in case_map.get("semantic_hints", [])
        if isinstance(item, dict) and isinstance(item.get("filename"), str)
    }
    for block in case_map.get("file_blocks", []):
        if not isinstance(block, dict):
            continue
        path = block.get("path")
        if not isinstance(path, str) or not path:
            continue
        status = statuses.setdefault(
            path,
            {
                "hinted": path in hinted_paths,
                "discovered": False,
                "read": False,
                "grep_hit": False,
                "lsp_touched": False,
                "selected": False,
                "ranges": [],
                "first_turn": block.get("first_turn"),
                "last_turn": block.get("last_turn"),
            },
        )
        kind = block.get("block_kind")
        if kind == "discover":
            status["discovered"] = True
        elif kind == "read":
            status["read"] = True
        elif kind == "grep_hit":
            status["grep_hit"] = True
        elif kind in {"lsp_nav", "lsp_search"}:
            status["lsp_touched"] = True
        elif kind == "select":
            status["selected"] = True

        ranges = block.get("ranges")
        if isinstance(ranges, list):
            for value in ranges:
                if (
                    isinstance(value, list)
                    and len(value) >= 2
                    and isinstance(value[0], int)
                    and isinstance(value[1], int)
                ):
                    status["ranges"].append([value[0], value[1]])

        first_turn = block.get("first_turn")
        last_turn = block.get("last_turn")
        if isinstance(first_turn, int):
            status["first_turn"] = (
                min(status["first_turn"], first_turn)
                if isinstance(status["first_turn"], int)
                else first_turn
            )
        if isinstance(last_turn, int):
            status["last_turn"] = (
                max(status["last_turn"], last_turn)
                if isinstance(status["last_turn"], int)
                else last_turn
            )

    for path in hinted_paths:
        if isinstance(path, str) and path and path not in statuses:
            statuses[path] = {
                "hinted": True,
                "discovered": False,
                "read": False,
                "grep_hit": False,
                "lsp_touched": False,
                "selected": False,
                "ranges": [],
                "first_turn": None,
                "last_turn": None,
            }

    for status in statuses.values():
        status["ranges"] = _merge_ranges(status["ranges"])
    return statuses


def _function_status(
    case_map: dict[str, Any],
) -> dict[tuple[str, str | None, str, tuple[int, int]], dict[str, Any]]:
    statuses: dict[tuple[str, str | None, str, tuple[int, int]], dict[str, Any]] = {}
    for block in case_map.get("function_blocks", []):
        if not isinstance(block, dict):
            continue
        key = _function_key(block)
        statuses[key] = {
            "path": block.get("path"),
            "function": block.get("function"),
            "class": block.get("class"),
            "range": block.get("range"),
            "signature": block.get("signature"),
            "first_turn": block.get("first_turn"),
            "last_turn": block.get("last_turn"),
            "access_kinds": block.get("access_kinds", []),
            "source_tools": block.get("source_tools", []),
        }
    return statuses


def _ground_truth_file_set(case_map: dict[str, Any]) -> set[str]:
    files = case_map.get("ground_truth_files", {})
    if not isinstance(files, dict):
        return set()
    return {path for path in files if isinstance(path, str)}


def _ground_truth_function_set(
    case_map: dict[str, Any],
) -> set[tuple[str, str | None, str, tuple[int, int]]]:
    functions = case_map.get("ground_truth_functions", [])
    result: set[tuple[str, str | None, str, tuple[int, int]]] = set()
    if not isinstance(functions, list):
        return result
    for item in functions:
        if not isinstance(item, dict):
            continue
        ranges = item.get("ranges", [])
        first_range = ranges[0] if isinstance(ranges, list) and ranges else [0, 0]
        if (
            isinstance(first_range, list)
            and len(first_range) >= 2
            and isinstance(first_range[0], int)
            and isinstance(first_range[1], int)
        ):
            range_key = (first_range[0], first_range[1])
        else:
            range_key = (0, 0)
        result.add(
            (
                str(item.get("path", "")),
                item.get("container") if isinstance(item.get("container"), str) else None,
                str(item.get("name", "")),
                range_key,
            )
        )
    return result


def _turn_curves(case_map: dict[str, Any]) -> dict[str, list[list[float | int]]]:
    turn_summaries = case_map.get("turn_summaries", [])
    if not isinstance(turn_summaries, list):
        return {
            "cumulative_unique_files": [],
            "cumulative_unique_functions": [],
            "ground_truth_file_recall": [],
            "ground_truth_function_recall": [],
        }

    gt_files = _ground_truth_file_set(case_map)
    gt_functions = _ground_truth_function_set(case_map)
    seen_files: set[str] = set()
    seen_functions: set[tuple[str, str | None, str, tuple[int, int]]] = set()

    file_curve: list[list[float | int]] = []
    function_curve: list[list[float | int]] = []
    file_recall_curve: list[list[float | int]] = []
    function_recall_curve: list[list[float | int]] = []

    for summary in turn_summaries:
        if not isinstance(summary, dict):
            continue
        turn = summary.get("turn")
        if not isinstance(turn, int):
            continue

        for path in summary.get("new_files", []):
            if isinstance(path, str):
                seen_files.add(path)
        for function in summary.get("new_functions", []):
            if isinstance(function, dict):
                seen_functions.add(_function_key(function))

        file_curve.append([turn, len(seen_files)])
        function_curve.append([turn, len(seen_functions)])
        file_recall = (len(seen_files & gt_files) / len(gt_files)) if gt_files else 0.0
        function_recall = (
            len(seen_functions & gt_functions) / len(gt_functions) if gt_functions else 0.0
        )
        file_recall_curve.append([turn, round(file_recall, 4)])
        function_recall_curve.append([turn, round(function_recall, 4)])

    return {
        "cumulative_unique_files": file_curve,
        "cumulative_unique_functions": function_curve,
        "ground_truth_file_recall": file_recall_curve,
        "ground_truth_function_recall": function_recall_curve,
    }


def build_case_map_compare(case_id: str, experiment_roots: list[Path]) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    present_case_maps: list[dict[str, Any]] = []
    for experiment_root in experiment_roots:
        bundle = load_search_map_bundle(experiment_root)
        label = _run_label(bundle)
        case_map = _case_index(bundle).get(case_id)
        if case_map is not None:
            present_case_maps.append(case_map)
        runs.append(
            {
                "run_label": label,
                "experiment": bundle.get("experiment", {}),
                "search_config": _search_config(bundle),
                "result_status": case_map.get("result_status", "missing_case")
                if isinstance(case_map, dict)
                else "missing_case",
                "case_map": case_map,
            }
        )

    if not runs:
        raise ValueError("No experiment roots provided")

    anchor = present_case_maps[0] if present_case_maps else {}
    file_sets = {
        run["run_label"]: set(run["case_map"].get("unique_files", []))
        for run in runs
        if isinstance(run.get("case_map"), dict)
    }
    function_sets = {
        run["run_label"]: {
            _function_key(function)
            for function in run["case_map"].get("unique_functions", [])
            if isinstance(function, dict)
        }
        for run in runs
        if isinstance(run.get("case_map"), dict)
    }

    available_file_sets = list(file_sets.values())
    shared_files = set.intersection(*available_file_sets) if available_file_sets else set()
    available_function_sets = list(function_sets.values())
    shared_function_keys = (
        set.intersection(*available_function_sets) if available_function_sets else set()
    )

    unique_files_by_run: dict[str, list[str]] = {}
    for label, file_set in file_sets.items():
        others: set[str] = set()
        for other_label, other_set in file_sets.items():
            if other_label != label:
                others |= other_set
        unique_files_by_run[label] = sorted(file_set - others)

    unique_functions_by_run: dict[str, list[dict[str, Any]]] = {}
    for label, function_set in function_sets.items():
        others: set[tuple[str, str | None, str, tuple[int, int]]] = set()
        for other_label, other_set in function_sets.items():
            if other_label != label:
                others |= other_set
        unique_keys = function_set - others
        source_case = next(
            (
                run["case_map"]
                for run in runs
                if run["run_label"] == label and isinstance(run.get("case_map"), dict)
            ),
            {},
        )
        unique_functions_by_run[label] = [
            _serialize_function(function)
            for function in source_case.get("unique_functions", [])
            if isinstance(function, dict) and _function_key(function) in unique_keys
        ]

    selected_sets = {
        run["run_label"]: set(run["case_map"].get("selected_files", []))
        for run in runs
        if isinstance(run.get("case_map"), dict)
    }
    hint_sets = {
        run["run_label"]: {
            item.get("filename")
            for item in run["case_map"].get("semantic_hints", [])
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        }
        for run in runs
        if isinstance(run.get("case_map"), dict)
    }
    selected_overlap = sorted(set.intersection(*selected_sets.values())) if selected_sets else []
    hint_overlap = sorted(set.intersection(*hint_sets.values())) if hint_sets else []

    path_matrix_rows: list[dict[str, Any]] = []
    all_paths = sorted(
        {
            path
            for run in runs
            for path in (
                (
                    set(_path_status(run["case_map"]).keys())
                    | set(run["case_map"].get("unique_files", []))
                )
                if isinstance(run.get("case_map"), dict)
                else set()
            )
        }
    )
    for path in all_paths:
        row = {
            "path": path,
            "ground_truth": path in _ground_truth_file_set(anchor),
            "runs": {},
        }
        for run in runs:
            case_map = run.get("case_map")
            if not isinstance(case_map, dict):
                row["runs"][run["run_label"]] = {"status": "missing_case"}
                continue
            statuses = _path_status(case_map)
            row["runs"][run["run_label"]] = statuses.get(
                path,
                {
                    "hinted": False,
                    "discovered": False,
                    "read": False,
                    "grep_hit": False,
                    "lsp_touched": False,
                    "selected": False,
                    "ranges": [],
                    "first_turn": None,
                    "last_turn": None,
                },
            )
        path_matrix_rows.append(row)

    function_matrix_rows: list[dict[str, Any]] = []
    all_function_keys = sorted(
        {key for function_set in function_sets.values() for key in function_set},
        key=lambda item: (item[0], item[3][0], item[1] or "", item[2]),
    )
    for key in all_function_keys:
        row = {
            "path": key[0],
            "function": key[2],
            "class": key[1],
            "range": [key[3][0], key[3][1]],
            "ground_truth": key in _ground_truth_function_set(anchor),
            "runs": {},
        }
        for run in runs:
            case_map = run.get("case_map")
            if not isinstance(case_map, dict):
                row["runs"][run["run_label"]] = {"status": "missing_case"}
                continue
            statuses = _function_status(case_map)
            row["runs"][run["run_label"]] = statuses.get(key, {"status": "missing_function"})
        function_matrix_rows.append(row)

    turn_curves = {
        run["run_label"]: _turn_curves(run["case_map"])
        for run in runs
        if isinstance(run.get("case_map"), dict)
    }

    shared_functions = []
    if present_case_maps:
        anchor_case = present_case_maps[0]
        shared_functions = [
            _serialize_function(function)
            for function in anchor_case.get("unique_functions", [])
            if isinstance(function, dict) and _function_key(function) in shared_function_keys
        ]

    return {
        "schema_version": CASE_MAP_COMPARE_SCHEMA_VERSION,
        "kind": "case_map_compare",
        "case_id": case_id,
        "query": anchor.get("query"),
        "repo": anchor.get("repo"),
        "ground_truth": {
            "files": anchor.get("ground_truth_files", {}),
            "functions": anchor.get("ground_truth_functions", []),
            "context_files": anchor.get("ground_truth_context_files", {}),
        },
        "runs": runs,
        "comparisons": {
            "shared_files": sorted(shared_files),
            "unique_files_by_run": unique_files_by_run,
            "shared_functions": shared_functions,
            "unique_functions_by_run": unique_functions_by_run,
            "selected_overlap": selected_overlap,
            "hint_overlap": hint_overlap,
            "path_matrix": path_matrix_rows,
            "function_matrix": function_matrix_rows,
            "turn_curves": turn_curves,
        },
    }


def _format_path_status_cell(status: dict[str, Any]) -> str:
    if status.get("status") == "missing_case":
        return "missing"
    tokens: list[str] = []
    if status.get("hinted"):
        tokens.append("H")
    if status.get("discovered"):
        tokens.append("D")
    if status.get("read"):
        tokens.append("R")
    if status.get("grep_hit"):
        tokens.append("G")
    if status.get("lsp_touched"):
        tokens.append("L")
    if status.get("selected"):
        tokens.append("S")
    return "".join(tokens) or "-"


def format_case_map_compare_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Case Map Comparison: {payload.get('case_id')}",
        "",
        f"**Repo**: {payload.get('repo')}",
        f"**Query**: {payload.get('query')}",
        "",
        "## Runs",
        "",
        "| Run | Status | Recall | Precision | Turns | Latency |",
        "|-----|--------|--------|-----------|-------|---------|",
    ]

    runs = payload.get("runs", [])
    for run in runs:
        case_map = run.get("case_map") or {}
        metrics = case_map.get("metrics_snapshot", {}) if isinstance(case_map, dict) else {}
        lines.append(
            f"| {run.get('run_label')} | {run.get('result_status')} | "
            f"{metrics.get('file_recall', '-')} | {metrics.get('file_precision', '-')} | "
            f"{metrics.get('turns_used', '-')} | {metrics.get('latency_s', '-')} |"
        )

    comparisons = payload.get("comparisons", {})
    lines.extend(
        [
            "",
            "## Shared Files",
            "",
            ", ".join(comparisons.get("shared_files", [])) or "(none)",
            "",
            "## Unique Files By Run",
            "",
        ]
    )
    for run_label, files in comparisons.get("unique_files_by_run", {}).items():
        lines.append(f"- {run_label}: {', '.join(files) if files else '(none)'}")

    lines.extend(
        [
            "",
            "## Path Matrix",
            "",
            "| Path | " + " | ".join(run.get("run_label", "") for run in runs) + " |",
            "|------|" + "|".join("---" for _ in runs) + "|",
        ]
    )
    for row in comparisons.get("path_matrix", []):
        cells = [
            _format_path_status_cell(row.get("runs", {}).get(run.get("run_label", ""), {}))
            for run in runs
        ]
        lines.append(f"| {row.get('path')} | " + " | ".join(cells) + " |")

    return "\n".join(lines)
