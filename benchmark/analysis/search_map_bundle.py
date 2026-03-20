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

SEARCH_MAP_BUNDLE_SCHEMA_VERSION = "1.1"
SEARCH_MAP_BUNDLE_FILENAME = "search_map.bundle.json"


def search_map_bundle_path(experiment_root: Path) -> Path:
    return experiment_reports_dir(experiment_root) / SEARCH_MAP_BUNDLE_FILENAME


def _load_json(path: Path | None) -> Any:
    # lgtm[py/path-injection]
    if path is None or not path.exists():
        return None
    # lgtm[py/path-injection]
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _persist_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _bundle_is_current(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("kind") != "search_map_bundle":
        return False
    if payload.get("schema_version") != SEARCH_MAP_BUNDLE_SCHEMA_VERSION:
        return False
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return False
    return all(
        isinstance(case, dict) and isinstance(case.get("exploration_tree"), dict) for case in cases
    )


def _case_index(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = bundle.get("cases")
    if not isinstance(cases, list):
        return {}

    index: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if isinstance(case_id, str) and case_id:
            index[case_id] = case
    return index


def _load_results_by_case(results_path: Path | None) -> dict[str, dict[str, Any]]:
    # lgtm[py/path-injection]
    if results_path is None or not results_path.exists():
        return {}

    results: dict[str, dict[str, Any]] = {}
    # lgtm[py/path-injection]
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


# ---------------------------------------------------------------------------
# Exploration tree helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_line_pair(raw_lines: Any) -> list[int] | None:
    if (
        isinstance(raw_lines, (list, tuple))
        and len(raw_lines) >= 2
        and isinstance(raw_lines[0], int)
        and isinstance(raw_lines[1], int)
        and raw_lines[0] > 0
        and raw_lines[1] >= raw_lines[0]
    ):
        return [raw_lines[0], raw_lines[1]]
    return None


def _range_label(raw_lines: Any) -> str | None:
    lines = _normalize_line_pair(raw_lines)
    if lines is None:
        return None
    return f"{lines[0]}-{lines[1]}"


def _preview_text(value: Any, *, limit: int = 180) -> str | None:
    if value is None:
        return None

    if isinstance(value, dict):
        if isinstance(value.get("error"), str) and value.get("error"):
            text = value["error"]
        else:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()

    if not text:
        return None

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    preview = first_line or text
    if len(preview) > limit:
        return preview[: limit - 3].rstrip() + "..."
    return preview


def _result_node_status(result_status: str) -> str:
    if result_status == "ok":
        return "ok"
    if result_status == "partial":
        return "partial"
    if result_status == "error":
        return "error"
    if result_status in {"missing_result", "missing_case"}:
        return "missing"
    return "info"


def _tool_node_status(tool_result: dict[str, Any] | None, children: list[dict[str, Any]]) -> str:
    if tool_result is None:
        return "missing"
    if tool_result.get("success") is False:
        return "error"
    if not children:
        return "info"
    return "ok"


def _turn_node_status(tool_nodes: list[dict[str, Any]]) -> str:
    if not tool_nodes:
        return "empty"

    statuses = {str(node.get("status", "info")) for node in tool_nodes}
    if statuses == {"error"}:
        return "error"
    if "error" in statuses or "missing" in statuses:
        return "partial"
    if statuses == {"empty"}:
        return "empty"
    if "ok" in statuses:
        return "ok"
    return "info"


def _parse_tool_args(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return {}
    raw_args = function.get("arguments", "{}")
    try:
        payload = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tool_label(tool_name: str) -> str:
    return tool_name or "unknown tool"


def _tool_detail(
    tool_name: str, args: dict[str, Any], tool_result: dict[str, Any] | None
) -> str | None:
    details: list[str] = []

    if tool_name in {"grep_search", "search_symbol"}:
        query = args.get("query")
        if isinstance(query, str) and query:
            details.append(f"query: {query}")
    elif tool_name in {"view_file", "view_directory", "glob"}:
        path = args.get("path")
        if isinstance(path, str) and path:
            details.append(f"path: {path}")
        view_range = _range_label(args.get("view_range"))
        if view_range:
            details.append(f"range: {view_range}")
    elif tool_name == "find_symbol":
        path = args.get("file")
        if isinstance(path, str) and path:
            line = _safe_int(args.get("line"))
            details.append(f"target: {path}:{line}" if line is not None else f"target: {path}")
    elif tool_name == "bash":
        command = args.get("command")
        if isinstance(command, str) and command:
            details.append(f"command: {command}")
    elif tool_name == "report_back":
        files = args.get("files")
        if isinstance(files, dict):
            details.append(f"files: {len(files)}")

    if isinstance(tool_result, dict):
        latency_ms = _safe_float(tool_result.get("latency_ms"))
        if latency_ms is not None:
            details.append(f"latency: {latency_ms:.1f} ms")
        if tool_result.get("success") is False:
            preview = _preview_text(tool_result.get("result"))
            if preview:
                details.append(f"error: {preview}")
        elif not details:
            preview = _preview_text(tool_result.get("result"))
            if preview:
                details.append(f"result: {preview}")

    return "\n".join(details) if details else None


def _llm_content_preview(turn_entry: dict[str, Any]) -> str | None:
    llm_response = turn_entry.get("llm_response")
    if not isinstance(llm_response, dict):
        return None
    choices = llm_response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    return _preview_text(message.get("content"))


def _event_detail(event: dict[str, Any]) -> str | None:
    details: list[str] = []
    access_type = event.get("access_type")
    if isinstance(access_type, str) and access_type:
        details.append(access_type)
    line_range = _range_label(event.get("lines"))
    if line_range:
        details.append(f"lines: {line_range}")
    intent = event.get("tool_query") or event.get("symbol_name") or event.get("tool_command")
    if isinstance(intent, str) and intent:
        details.append(f"intent: {intent}")
    return "\n".join(details) if details else None


def _function_label(function: dict[str, Any]) -> str:
    class_name = function.get("class")
    name = function.get("function")
    if isinstance(class_name, str) and class_name and isinstance(name, str) and name:
        return f"{class_name}.{name}"
    return str(name or "(anonymous function)")


def _function_detail(function: dict[str, Any]) -> str | None:
    path = function.get("path")
    range_label = _range_label(function.get("range"))
    if isinstance(path, str) and path and range_label:
        return f"{path}:{range_label}"
    if isinstance(path, str) and path:
        return path
    return range_label


def _event_children(
    case_id: str, turn: int, tool_node_id: str, event: dict[str, Any], event_index: int
) -> list[dict[str, Any]]:
    functions = event.get("functions")
    children: list[dict[str, Any]] = []
    if not isinstance(functions, list):
        return children

    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            continue
        children.append(
            {
                "id": f"{tool_node_id}:event:{event_index}:function:{function_index}",
                "kind": "function",
                "status": "ok" if event.get("access_type") != "select" else "selected",
                "label": _function_label(function),
                "detail": _function_detail(function),
                "turn": turn,
                "path": function.get("path"),
                "lines": _normalize_line_pair(function.get("range")),
                "children": [],
            }
        )
    return children


def _event_nodes(
    case_id: str, turn: int, tool_node_id: str, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for event_index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        path = event.get("path")
        if not isinstance(path, str) or not path:
            continue
        nodes.append(
            {
                "id": f"{tool_node_id}:event:{event_index}",
                "kind": "path" if path.endswith("/") else "file",
                "status": "ok" if event.get("access_type") != "select" else "selected",
                "label": path,
                "detail": _event_detail(event),
                "turn": turn,
                "tool_name": event.get("tool_name"),
                "path": path,
                "lines": _normalize_line_pair(event.get("lines")),
                "children": _event_children(case_id, turn, tool_node_id, event, event_index),
            }
        )
    return nodes


def _group_events_by_tool(
    events: list[dict[str, Any]],
) -> dict[tuple[int, str | None, str], list[dict[str, Any]]]:
    grouped: dict[tuple[int, str | None, str], list[dict[str, Any]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        turn = event.get("turn")
        tool_name = event.get("tool_name")
        if (
            not isinstance(turn, int)
            or turn <= 0
            or not isinstance(tool_name, str)
            or not tool_name
        ):
            continue
        tool_call_id = event.get("tool_call_id")
        normalized_tool_call_id = (
            tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None
        )
        grouped.setdefault((turn, normalized_tool_call_id, tool_name), []).append(event)
    return grouped


def _build_turn_detail(turn: int, turn_entry: dict[str, Any], tool_count: int) -> str | None:
    details: list[str] = [f"tools: {tool_count}"]
    latency_ms = _safe_float(turn_entry.get("llm_latency_ms"))
    if latency_ms is not None:
        details.append(f"llm: {latency_ms:.1f} ms")
    usage = (turn_entry.get("llm_response") or {}).get("usage") or {}
    prompt_tokens = _safe_int(usage.get("prompt_tokens"))
    completion_tokens = _safe_int(usage.get("completion_tokens"))
    if prompt_tokens is not None:
        details.append(f"prompt: {prompt_tokens}")
    if completion_tokens is not None:
        details.append(f"completion: {completion_tokens}")
    return "\n".join(details) if details else None


def _build_result_detail(metrics_snapshot: dict[str, Any], result_status: str) -> str | None:
    details: list[str] = [f"status: {result_status}"]
    for key, label in (
        ("file_recall", "recall"),
        ("file_precision", "precision"),
        ("turns_used", "turns"),
        ("latency_s", "latency_s"),
        ("returned_files_count", "returned_files"),
    ):
        value = metrics_snapshot.get(key)
        if value is not None:
            details.append(f"{label}: {value}")
    error = metrics_snapshot.get("error")
    if isinstance(error, str) and error:
        details.append(f"error: {error}")
    return "\n".join(details)


def _build_result_node(
    case_id: str,
    result_status: str,
    metrics_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"case:{case_id}:result",
        "kind": "result",
        "status": _result_node_status(result_status),
        "label": f"Result: {result_status}",
        "detail": _build_result_detail(metrics_snapshot, result_status),
        "children": [],
    }


def _build_turn_node(
    case_id: str,
    turn_index: int,
    turn_entry: dict[str, Any],
    events_by_tool: dict[tuple[int, str | None, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    tool_nodes: list[dict[str, Any]] = []

    tool_calls_raw = turn_entry.get("tool_calls_raw", [])
    tool_results = turn_entry.get("tool_results", [])
    tool_results_by_id = {
        item.get("id"): item
        for item in tool_results
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    unnamed_tool_results_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("id"), str) and item.get("id"):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            unnamed_tool_results_by_name.setdefault(name, []).append(item)

    seen_tool_keys: set[tuple[int, str | None, str]] = set()
    for call_index, tool_call in enumerate(tool_calls_raw):
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        tool_name = function.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue

        tool_call_id = tool_call.get("id")
        normalized_tool_call_id = (
            tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None
        )
        key = (turn_index, normalized_tool_call_id, tool_name)
        seen_tool_keys.add(key)
        args = _parse_tool_args(tool_call)
        tool_result = (
            tool_results_by_id.get(normalized_tool_call_id) if normalized_tool_call_id else None
        )
        if tool_result is None and normalized_tool_call_id is None:
            same_name_results = unnamed_tool_results_by_name.get(tool_name, [])
            tool_result = same_name_results.pop(0) if same_name_results else None
        child_nodes = _event_nodes(
            case_id,
            turn_index,
            f"case:{case_id}:turn:{turn_index}:tool:{call_index}",
            events_by_tool.get(key, []),
        )
        tool_nodes.append(
            {
                "id": f"case:{case_id}:turn:{turn_index}:tool:{call_index}",
                "kind": "tool",
                "status": _tool_node_status(tool_result, child_nodes),
                "label": _tool_label(tool_name),
                "detail": _tool_detail(tool_name, args, tool_result),
                "turn": turn_index,
                "tool_name": tool_name,
                "latency_ms": _safe_float(tool_result.get("latency_ms"))
                if isinstance(tool_result, dict)
                else None,
                "is_success": bool(tool_result.get("success", True))
                if isinstance(tool_result, dict)
                else None,
                "children": child_nodes,
            }
        )

    orphan_results = [
        item
        for item in tool_results
        if isinstance(item, dict)
        and (item.get("id"), item.get("name")) != (None, None)
        and (
            turn_index,
            item.get("id") if isinstance(item.get("id"), str) and item.get("id") else None,
            str(item.get("name") or ""),
        )
        not in seen_tool_keys
    ]
    for orphan_index, tool_result in enumerate(orphan_results, start=len(tool_nodes)):
        tool_name = str(tool_result.get("name") or "unknown tool")
        tool_call_id = tool_result.get("id")
        normalized_tool_call_id = (
            tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None
        )
        key = (turn_index, normalized_tool_call_id, tool_name)
        child_nodes = _event_nodes(
            case_id,
            turn_index,
            f"case:{case_id}:turn:{turn_index}:tool:{orphan_index}",
            events_by_tool.get(key, []),
        )
        tool_nodes.append(
            {
                "id": f"case:{case_id}:turn:{turn_index}:tool:{orphan_index}",
                "kind": "tool",
                "status": _tool_node_status(tool_result, child_nodes),
                "label": _tool_label(tool_name),
                "detail": _tool_detail(tool_name, {}, tool_result),
                "turn": turn_index,
                "tool_name": tool_name,
                "latency_ms": _safe_float(tool_result.get("latency_ms")),
                "is_success": bool(tool_result.get("success", True)),
                "children": child_nodes,
            }
        )

    if not tool_nodes:
        note_preview = _llm_content_preview(turn_entry)
        tool_nodes.append(
            {
                "id": f"case:{case_id}:turn:{turn_index}:note",
                "kind": "note",
                "status": "empty",
                "label": "No tool calls returned",
                "detail": note_preview,
                "turn": turn_index,
                "children": [],
            }
        )

    return {
        "id": f"case:{case_id}:turn:{turn_index}",
        "kind": "turn",
        "status": _turn_node_status(tool_nodes),
        "label": f"Turn {turn_index}",
        "detail": _build_turn_detail(turn_index, turn_entry, len(tool_nodes)),
        "turn": turn_index,
        "children": tool_nodes,
    }


def _build_exploration_tree(
    *,
    case_id: str,
    query: str,
    repo: str | None,
    turns: list[dict[str, Any]],
    events: list[dict[str, Any]],
    metrics_snapshot: dict[str, Any],
    result_status: str,
) -> dict[str, Any]:
    events_by_tool = _group_events_by_tool(events)
    turn_nodes = [
        _build_turn_node(case_id, turn, entry, events_by_tool)
        for turn, entry in (
            (
                entry.get("turn")
                if isinstance(entry.get("turn"), int) and entry.get("turn", 0) > 0
                else index,
                entry,
            )
            for index, entry in enumerate(turns, 1)
            if isinstance(entry, dict)
        )
    ]

    if not turn_nodes:
        turn_nodes = [
            {
                "id": f"case:{case_id}:note:no-trace",
                "kind": "note",
                "status": "empty",
                "label": "No trace turns recorded",
                "detail": None,
                "children": [],
            }
        ]

    detail_lines: list[str] = []
    if repo:
        detail_lines.append(f"repo: {repo}")
    if query:
        detail_lines.append(f"query: {query}")

    children = turn_nodes + [_build_result_node(case_id, result_status, metrics_snapshot)]
    return {
        "id": f"case:{case_id}",
        "kind": "case",
        "status": _result_node_status(result_status),
        "label": case_id,
        "detail": "\n".join(detail_lines) if detail_lines else None,
        "children": children,
    }


def _build_exploration_tree_from_case_payload(case_payload: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case_payload.get("case_id") or "")
    query = str(case_payload.get("query") or "")
    repo = case_payload.get("repo")
    repo_value = repo if isinstance(repo, str) else None
    result_status = str(case_payload.get("result_status") or "missing_result")
    metrics_snapshot = (
        case_payload.get("metrics_snapshot")
        if isinstance(case_payload.get("metrics_snapshot"), dict)
        else {"result_status": result_status}
    )
    turns = case_payload.get("turn_summaries")
    events = case_payload.get("events")
    if not isinstance(turns, list):
        turns = []
    if not isinstance(events, list):
        events = []

    normalized_turns: list[dict[str, Any]] = []
    for turn_summary in turns:
        if not isinstance(turn_summary, dict):
            continue
        tool_names = turn_summary.get("tool_names")
        normalized_turns.append(
            {
                "turn": turn_summary.get("turn"),
                "llm_latency_ms": turn_summary.get("llm_latency_ms"),
                "llm_response": {
                    "usage": {
                        "prompt_tokens": turn_summary.get("prompt_tokens"),
                        "completion_tokens": turn_summary.get("completion_tokens"),
                    }
                },
                "tool_calls_raw": [
                    {
                        "function": {"name": name, "arguments": "{}"},
                    }
                    for name in (tool_names if isinstance(tool_names, list) else [])
                    if isinstance(name, str)
                ],
                "tool_results": [
                    {"name": name, "success": True}
                    for name in (tool_names if isinstance(tool_names, list) else [])
                    if isinstance(name, str)
                ],
            }
        )

    normalized_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        normalized_events.append(dict(event))

    return _build_exploration_tree(
        case_id=case_id,
        query=query,
        repo=repo_value,
        turns=normalized_turns,
        events=normalized_events,
        metrics_snapshot=metrics_snapshot,
        result_status=result_status,
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
    metrics_snapshot = _build_metrics_snapshot(result)
    result_status = _result_status(result)

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

    payload = {
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
        "metrics_snapshot": metrics_snapshot,
        "result_status": result_status,
    }
    payload["exploration_tree"] = _build_exploration_tree(
        case_id=search_map.case_id,
        query=query,
        repo=repo,
        turns=turns,
        events=events,
        metrics_snapshot=metrics_snapshot,
        result_status=result_status,
    )
    return payload


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
        # lgtm[py/path-injection]
        "report_path": str(report_path)
        if report_path is not None and report_path.exists()
        else None,
        # lgtm[py/path-injection]
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


def rebuild_search_map_bundle(experiment_root: Path) -> dict[str, Any]:
    payload = build_search_map_bundle_from_experiment(experiment_root)
    _persist_json(search_map_bundle_path(experiment_root), payload)
    return payload


def _upgrade_existing_bundle(existing: dict[str, Any]) -> dict[str, Any]:
    payload = dict(existing)
    payload["schema_version"] = SEARCH_MAP_BUNDLE_SCHEMA_VERSION

    cases = payload.get("cases")
    if not isinstance(cases, list):
        payload["cases"] = []
        return payload

    upgraded_cases: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        upgraded_case = dict(case)
        upgraded_case["exploration_tree"] = _build_exploration_tree_from_case_payload(upgraded_case)
        upgraded_cases.append(upgraded_case)
    payload["cases"] = upgraded_cases
    return payload


def load_search_map_bundle(experiment_root: Path) -> dict[str, Any]:
    bundle_path = search_map_bundle_path(experiment_root)
    existing = _load_json(bundle_path)
    if _bundle_is_current(existing):
        return existing

    traces_dir = experiment_root / "traces"
    if traces_dir.is_dir():
        return rebuild_search_map_bundle(experiment_root)

    if isinstance(existing, dict) and existing.get("kind") == "search_map_bundle":
        upgraded = _upgrade_existing_bundle(existing)
        _persist_json(bundle_path, upgraded)
        return upgraded

    raise FileNotFoundError(f"No search_map bundle or traces found for {experiment_root}")


def load_search_map_case(experiment_root: Path, case_id: str) -> dict[str, Any]:
    bundle = load_search_map_bundle(experiment_root)
    case_payload = _case_index(bundle).get(case_id)
    if case_payload is None:
        raise FileNotFoundError(f"Case {case_id!r} not found in {experiment_root}")
    return case_payload


def intersect_case_ids(experiment_roots: list[Path]) -> list[str]:
    if not experiment_roots:
        return []

    case_sets = [set(_case_index(load_search_map_bundle(root)).keys()) for root in experiment_roots]
    if not case_sets:
        return []
    return sorted(set.intersection(*case_sets))
