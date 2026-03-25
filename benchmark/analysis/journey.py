import json
from typing import Any

_CANDIDATE_ACCESS_TYPES = {"discover", "grep_hit", "lsp_nav", "lsp_search"}
_VISIBLE_ARTIFACT_ACCESS_TYPES = {"read", "select"}
_HINT_ACCESS_TYPE = "hint"


def _normalize_range(raw_range: Any) -> list[int] | None:
    if (
        isinstance(raw_range, (list, tuple))
        and len(raw_range) >= 2
        and isinstance(raw_range[0], int)
        and isinstance(raw_range[1], int)
        and raw_range[0] > 0
        and raw_range[1] >= raw_range[0]
    ):
        return [raw_range[0], raw_range[1]]
    return None


def _normalize_ranges(raw_ranges: Any) -> list[list[int]]:
    if not isinstance(raw_ranges, list):
        return []
    normalized: list[list[int]] = []
    for raw_range in raw_ranges:
        item = _normalize_range(raw_range)
        if item is not None:
            normalized.append(item)
    return normalized


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


def _is_file_path(path: Any) -> bool:
    return isinstance(path, str) and bool(path) and path != "." and not path.endswith("/")


def _unique_sorted_paths(paths: list[str]) -> list[str]:
    return sorted({path for path in paths if _is_file_path(path)})


def _empty_status_flags() -> dict[str, bool]:
    return {
        "ground_truth": False,
        "ground_truth_context": False,
        "hinted": False,
        "candidate": False,
        "inspected": False,
        "selected": False,
        "hit": False,
        "degraded": False,
    }


def _query_node_id() -> str:
    return "query"


def _result_node_id() -> str:
    return "result"


def _tool_call_node_id(turn: int, call_index: int, tool_name: str) -> str:
    return f"tool:{turn}:{call_index}:{tool_name or 'unknown'}"


def _candidate_set_node_id(turn: int, call_index: int, access_type: str) -> str:
    return f"candidate:{turn}:{call_index}:{access_type}"


def _hint_candidate_set_node_id() -> str:
    return "candidate:hinted"


def _file_node_id(path: str) -> str:
    return f"file:{path}"


def _class_node_id(path: str, class_name: str) -> str:
    return f"class:{path}:{class_name}"


def _function_node_id(
    path: str,
    class_name: str | None,
    function_name: str,
    line_range: list[int] | None,
) -> str:
    start = line_range[0] if line_range else 0
    end = line_range[1] if line_range else 0
    return f"function:{path}:{class_name or ''}:{function_name}:{start}:{end}"


def _short_json(value: Any) -> str | None:
    if value in (None, {}, [], ""):
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return None
    if len(text) > 220:
        return text[:217] + "..."
    return text


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


def _iter_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                strings.append(key)
            strings.extend(_iter_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_iter_strings(item))
    return strings


def _event_ranges(event: dict[str, Any]) -> list[list[int]]:
    ranges = _normalize_ranges(event.get("ranges"))
    if ranges:
        return ranges
    single = _normalize_range(event.get("lines"))
    return [single] if single is not None else []


def _function_ref_from_runtime(item: dict[str, Any]) -> dict[str, Any] | None:
    path = item.get("path")
    function_name = item.get("function")
    if not _is_file_path(path) or not isinstance(function_name, str) or not function_name:
        return None
    class_name = item.get("class") if isinstance(item.get("class"), str) else None
    line_range = _normalize_range(item.get("range"))
    return {
        "path": path,
        "class": class_name,
        "function": function_name,
        "range": line_range,
        "label": f"{class_name}.{function_name}" if class_name else function_name,
    }


def _function_ref_from_ground_truth(item: dict[str, Any]) -> dict[str, Any] | None:
    path = item.get("path")
    function_name = item.get("name")
    if not _is_file_path(path) or not isinstance(function_name, str) or not function_name:
        return None
    class_name = item.get("container") if isinstance(item.get("container"), str) else None
    ranges = _normalize_ranges(item.get("ranges"))
    line_range = ranges[0] if ranges else None
    return {
        "path": path,
        "class": class_name,
        "function": function_name,
        "range": line_range,
        "label": f"{class_name}.{function_name}" if class_name else function_name,
    }


def _function_key_from_ref(ref: dict[str, Any]) -> tuple[str, str | None, str, tuple[int, int]]:
    line_range = ref.get("range") if isinstance(ref.get("range"), list) else [0, 0]
    start = int(line_range[0]) if len(line_range) >= 2 else 0
    end = int(line_range[1]) if len(line_range) >= 2 else 0
    return (ref["path"], ref.get("class"), ref["function"], (start, end))


def _ground_truth_function_keys(
    case_data: dict[str, Any],
) -> set[tuple[str, str | None, str, tuple[int, int]]]:
    result: set[tuple[str, str | None, str, tuple[int, int]]] = set()
    for item in case_data.get("ground_truth_functions") or []:
        if not isinstance(item, dict):
            continue
        ref = _function_ref_from_ground_truth(item)
        if ref is None:
            continue
        result.add(_function_key_from_ref(ref))
    return result


def _tool_result_maps(
    tool_results: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        tool_result_id = item.get("id")
        if isinstance(tool_result_id, str) and tool_result_id:
            by_id[tool_result_id] = item
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            by_name.setdefault(name, []).append(item)
    return by_id, by_name


def _find_tool_result(
    *,
    tool_call: dict[str, Any],
    tool_name: str,
    tool_results_by_id: dict[str, dict[str, Any]],
    unnamed_tool_results_by_name: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    tool_call_id = tool_call.get("id")
    if isinstance(tool_call_id, str) and tool_call_id:
        return tool_results_by_id.get(tool_call_id)
    same_name_results = unnamed_tool_results_by_name.get(tool_name, [])
    return same_name_results.pop(0) if same_name_results else None


def _event_groups(
    events: list[dict[str, Any]],
) -> tuple[
    dict[tuple[int, str | None, str], list[dict[str, Any]]],
    dict[tuple[int, str], list[dict[str, Any]]],
]:
    by_id: dict[tuple[int, str | None, str], list[dict[str, Any]]] = {}
    by_name: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for index, event in enumerate(events):
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
        event_copy = dict(event)
        event_copy.setdefault("event_id", f"event:{turn}:{tool_name}:{index}")
        tool_call_id = (
            event.get("tool_call_id") if isinstance(event.get("tool_call_id"), str) else None
        )
        by_id.setdefault((turn, tool_call_id, tool_name), []).append(event_copy)
        by_name.setdefault((turn, tool_name), []).append(event_copy)
    return by_id, by_name


def _candidate_label(access_type: str) -> str:
    if access_type == _HINT_ACCESS_TYPE:
        return "Semantic Hints"
    if access_type == "discover":
        return "Discoveries"
    if access_type == "grep_hit":
        return "Grep Hits"
    if access_type == "lsp_nav":
        return "LSP Navigation"
    if access_type == "lsp_search":
        return "LSP Search Hits"
    return access_type


class _JourneyGraphState:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def _base_node(self, *, node_id: str, kind: str, label: str) -> dict[str, Any]:
        return {
            "id": node_id,
            "kind": kind,
            "label": label,
            "turn": None,
            "first_seen_turn": None,
            "last_seen_turn": None,
            "path": None,
            "class_name": None,
            "function_name": None,
            "range": None,
            "ranges": [],
            "tool_name": None,
            "tool_call_id": None,
            "args_excerpt": None,
            "is_success": None,
            "status_flags": _empty_status_flags(),
            "access_types": [],
            "source_tool_names": [],
            "source_event_ids": [],
            "candidate_count": None,
            "candidate_paths": [],
            "preview_paths": [],
            "candidate_access_type": None,
        }

    def ensure_query(self, label: str) -> str:
        node_id = _query_node_id()
        self.nodes.setdefault(
            node_id, self._base_node(node_id=node_id, kind="query", label=label or "Query")
        )
        if label:
            self.nodes[node_id]["label"] = label
        return node_id

    def ensure_result(self, result_status: str) -> str:
        node_id = _result_node_id()
        self.nodes.setdefault(
            node_id,
            self._base_node(
                node_id=node_id,
                kind="result",
                label=f"Result: {result_status}" if result_status else "Result",
            ),
        )
        return node_id

    def ensure_tool_call(
        self,
        *,
        turn: int,
        call_index: int,
        tool_name: str,
        tool_call_id: str | None,
        args: dict[str, Any],
        is_success: bool | None,
    ) -> str:
        node_id = _tool_call_node_id(turn, call_index, tool_name)
        node = self.nodes.setdefault(
            node_id,
            self._base_node(node_id=node_id, kind="tool_call", label=tool_name or "unknown tool"),
        )
        node["turn"] = turn
        node["first_seen_turn"] = turn
        node["last_seen_turn"] = turn
        node["tool_name"] = tool_name or "unknown tool"
        node["tool_call_id"] = tool_call_id
        node["args_excerpt"] = _short_json(args)
        node["is_success"] = is_success
        if tool_name and tool_name not in node["source_tool_names"]:
            node["source_tool_names"].append(tool_name)
        return node_id

    def ensure_candidate_set(
        self,
        *,
        turn: int | None,
        call_index: int | None,
        access_type: str,
        tool_name: str | None,
        paths: list[str],
        event_ids: list[str],
        hinted: bool,
        degraded: bool,
    ) -> str:
        node_id = (
            _hint_candidate_set_node_id()
            if access_type == _HINT_ACCESS_TYPE
            else _candidate_set_node_id(turn or 0, call_index or 0, access_type)
        )
        label = _candidate_label(access_type)
        node = self.nodes.setdefault(
            node_id,
            self._base_node(node_id=node_id, kind="candidate_set", label=label),
        )
        if isinstance(turn, int) and turn > 0:
            node["turn"] = turn
            self.update_turn_range(node_id, turn)
        node["tool_name"] = tool_name
        node["candidate_access_type"] = access_type
        node["candidate_paths"] = _unique_sorted_paths((node.get("candidate_paths") or []) + paths)
        node["candidate_count"] = len(node["candidate_paths"])
        node["preview_paths"] = node["candidate_paths"][:6]
        if tool_name and tool_name not in node["source_tool_names"]:
            node["source_tool_names"].append(tool_name)
        for event_id in event_ids:
            if event_id not in node["source_event_ids"]:
                node["source_event_ids"].append(event_id)
        flags = node["status_flags"]
        if hinted:
            flags["hinted"] = True
        else:
            flags["candidate"] = True
        if degraded:
            flags["degraded"] = True
        if access_type not in node["access_types"]:
            node["access_types"].append(access_type)
        return node_id

    def ensure_file(self, path: str) -> str:
        node_id = _file_node_id(path)
        node = self.nodes.setdefault(
            node_id,
            self._base_node(node_id=node_id, kind="file", label=path.split("/")[-1] or path),
        )
        node["path"] = path
        return node_id

    def ensure_class(self, path: str, class_name: str) -> str:
        file_id = self.ensure_file(path)
        node_id = _class_node_id(path, class_name)
        node = self.nodes.setdefault(
            node_id,
            self._base_node(node_id=node_id, kind="class", label=class_name),
        )
        node["path"] = path
        node["class_name"] = class_name
        self.ensure_edge(file_id, node_id, kind="contains")
        return node_id

    def ensure_function(
        self,
        *,
        path: str,
        class_name: str | None,
        function_name: str,
        line_range: list[int] | None,
        label: str,
    ) -> str:
        parent_id = self.ensure_class(path, class_name) if class_name else self.ensure_file(path)
        node_id = _function_node_id(path, class_name, function_name, line_range)
        node = self.nodes.setdefault(
            node_id,
            self._base_node(node_id=node_id, kind="function", label=label),
        )
        node["path"] = path
        node["class_name"] = class_name
        node["function_name"] = function_name
        if line_range is not None:
            node["range"] = line_range
            node["ranges"] = _merge_ranges(
                _normalize_ranges((node.get("ranges") or []) + [line_range])
            )
        self.ensure_edge(parent_id, node_id, kind="contains")
        return node_id

    def update_turn_range(self, node_id: str, turn: int | None) -> None:
        if not isinstance(turn, int) or turn <= 0:
            return
        node = self.nodes[node_id]
        first_seen = node.get("first_seen_turn")
        last_seen = node.get("last_seen_turn")
        node["first_seen_turn"] = turn if not isinstance(first_seen, int) else min(first_seen, turn)
        node["last_seen_turn"] = turn if not isinstance(last_seen, int) else max(last_seen, turn)

    def add_ranges(self, node_id: str, ranges: list[list[int]]) -> None:
        if not ranges:
            return
        node = self.nodes[node_id]
        existing = _normalize_ranges(node.get("ranges"))
        merged = _merge_ranges(existing + [item[:] for item in ranges])
        node["ranges"] = merged
        node["range"] = merged[0] if merged else node.get("range")

    def touch_node(
        self,
        node_id: str,
        *,
        turn: int | None,
        access_type: str | None = None,
        tool_name: str | None = None,
        event_id: str | None = None,
        ranges: list[list[int]] | None = None,
        hinted: bool = False,
        candidate: bool = False,
        inspected: bool = False,
        selected: bool = False,
        ground_truth: bool = False,
        ground_truth_context: bool = False,
        degraded: bool = False,
    ) -> None:
        node = self.nodes[node_id]
        if turn is not None:
            self.update_turn_range(node_id, turn)
        if ranges:
            self.add_ranges(node_id, ranges)
        flags = node["status_flags"]
        if hinted:
            flags["hinted"] = True
        if candidate:
            flags["candidate"] = True
        if inspected:
            flags["inspected"] = True
        if selected:
            flags["selected"] = True
        if ground_truth:
            flags["ground_truth"] = True
        if ground_truth_context:
            flags["ground_truth_context"] = True
        if degraded:
            flags["degraded"] = True
        flags["hit"] = bool(flags["ground_truth"] and (flags["inspected"] or flags["selected"]))
        if access_type and access_type not in node["access_types"]:
            node["access_types"].append(access_type)
        if tool_name and tool_name not in node["source_tool_names"]:
            node["source_tool_names"].append(tool_name)
        if event_id and event_id not in node["source_event_ids"]:
            node["source_event_ids"].append(event_id)

    def ensure_edge(
        self,
        source: str,
        target: str,
        *,
        kind: str,
        turn: int | None = None,
        tool_name: str | None = None,
        access_type: str | None = None,
        detail: str | None = None,
        is_final_path: bool | None = None,
    ) -> str:
        edge_id = f"{kind}:{source}:{target}"
        edge = self.edges.get(edge_id)
        if edge is None:
            edge = {
                "id": edge_id,
                "kind": kind,
                "source": source,
                "target": target,
                "turns": [],
                "tool_names": [],
                "access_types": [],
                "detail": detail,
                "is_final_path": bool(is_final_path),
            }
            self.edges[edge_id] = edge
        if isinstance(turn, int) and turn > 0 and turn not in edge["turns"]:
            edge["turns"].append(turn)
        if tool_name and tool_name not in edge["tool_names"]:
            edge["tool_names"].append(tool_name)
        if access_type and access_type not in edge["access_types"]:
            edge["access_types"].append(access_type)
        if detail and not edge.get("detail"):
            edge["detail"] = detail
        if is_final_path:
            edge["is_final_path"] = True
        return edge_id

    def serialize_nodes(self) -> list[dict[str, Any]]:
        order = {
            "query": -1,
            "tool_call": 0,
            "candidate_set": 1,
            "file": 2,
            "class": 3,
            "function": 4,
            "result": 5,
        }
        result = []
        for node in self.nodes.values():
            serialized = dict(node)
            if not serialized.get("turn") and serialized.get("first_seen_turn"):
                serialized["turn"] = serialized["first_seen_turn"]
            result.append(serialized)
        return sorted(
            result,
            key=lambda item: (
                order.get(str(item.get("kind")), 99),
                int(item.get("turn") or 0),
                str(item.get("candidate_access_type") or ""),
                str(item.get("tool_name") or ""),
                str(item.get("path") or ""),
                str(item.get("class_name") or ""),
                str(item.get("function_name") or ""),
                str(item.get("label") or ""),
            ),
        )

    def serialize_edges(self) -> list[dict[str, Any]]:
        order = {
            "hint": 0,
            "next_step": 1,
            "causal_exact": 2,
            "causal_temporal": 3,
            "produced_candidates": 4,
            "inspects": 5,
            "selects": 6,
            "contains": 7,
            "converges": 8,
        }
        payloads: list[dict[str, Any]] = []
        for edge in self.edges.values():
            payload = dict(edge)
            payload["turns"] = sorted(
                turn for turn in payload.get("turns", []) if isinstance(turn, int) and turn > 0
            )
            payload["tool_names"] = sorted(
                name for name in payload.get("tool_names", []) if isinstance(name, str) and name
            )
            payload["access_types"] = sorted(
                name for name in payload.get("access_types", []) if isinstance(name, str) and name
            )
            payloads.append(payload)
        return sorted(
            payloads,
            key=lambda item: (
                order.get(str(item.get("kind")), 99),
                str(item.get("source") or ""),
                str(item.get("target") or ""),
            ),
        )


def _node_match_tokens(node: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for key in ("path", "label", "class_name", "function_name", "tool_name"):
        value = node.get(key)
        if isinstance(value, str) and value:
            tokens.append(value.lower())
    for path in node.get("candidate_paths") or []:
        if isinstance(path, str) and path:
            tokens.append(path.lower())
    return tokens


def _causal_source_ids(
    args: dict[str, Any],
    previous_context_node_ids: list[str],
    nodes: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    if not previous_context_node_ids:
        return [], []
    text_blob = "\n".join(item.lower() for item in _iter_strings(args))
    exact: list[str] = []
    for node_id in previous_context_node_ids:
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        tokens = _node_match_tokens(node)
        if tokens and any(token in text_blob for token in tokens):
            exact.append(node_id)
    if exact:
        return exact[:4], []

    temporal = [
        node_id
        for node_id in previous_context_node_ids
        if isinstance(nodes.get(node_id), dict)
        and nodes[node_id].get("kind") in {"candidate_set", "file", "class", "function"}
    ]
    return [], temporal[:3]


def _summary_base(
    turn: int,
    turn_entry: dict[str, Any],
    case_data: dict[str, Any],
) -> dict[str, Any]:
    turn_summaries = case_data.get("turn_summaries") or []
    for summary in turn_summaries:
        if isinstance(summary, dict) and summary.get("turn") == turn:
            return {
                "tool_names": [
                    name for name in summary.get("tool_names", []) if isinstance(name, str)
                ],
                "new_files": [
                    path for path in summary.get("new_files", []) if isinstance(path, str)
                ],
                "new_functions": [
                    item for item in summary.get("new_functions", []) if isinstance(item, dict)
                ],
                "selected_files": [
                    path for path in summary.get("selected_files", []) if isinstance(path, str)
                ],
                "llm_latency_ms": summary.get("llm_latency_ms")
                if summary.get("llm_latency_ms") is not None
                else turn_entry.get("llm_latency_ms"),
                "prompt_tokens": summary.get("prompt_tokens"),
                "completion_tokens": summary.get("completion_tokens"),
            }
    usage = (turn_entry.get("llm_response") or {}).get("usage") or {}
    tool_names: list[str] = []
    for tool_call in turn_entry.get("tool_calls_raw", []):
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            tool_names.append(function["name"])
    return {
        "tool_names": tool_names,
        "new_files": [],
        "new_functions": [],
        "selected_files": [],
        "llm_latency_ms": turn_entry.get("llm_latency_ms"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }


def _register_function_ref(
    state: _JourneyGraphState,
    *,
    ref: dict[str, Any],
    turn: int | None,
    access_type: str,
    tool_name: str | None,
    event_id: str | None,
    hinted: bool,
    selected: bool,
    ground_truth_keys: set[tuple[str, str | None, str, tuple[int, int]]],
    degraded: bool,
) -> list[str]:
    node_ids: list[str] = []
    gt_key = _function_key_from_ref(ref)
    class_name = ref.get("class")
    if isinstance(class_name, str) and class_name:
        class_id = state.ensure_class(ref["path"], class_name)
        state.touch_node(
            class_id,
            turn=turn,
            access_type=access_type,
            tool_name=tool_name,
            event_id=event_id,
            hinted=hinted,
            inspected=access_type == "read",
            selected=selected,
            ground_truth=gt_key in ground_truth_keys,
            degraded=degraded,
        )
        node_ids.append(class_id)

    function_id = state.ensure_function(
        path=ref["path"],
        class_name=ref.get("class"),
        function_name=ref["function"],
        line_range=ref.get("range"),
        label=ref["label"],
    )
    ranges = [ref["range"]] if isinstance(ref.get("range"), list) else []
    state.touch_node(
        function_id,
        turn=turn,
        access_type=access_type,
        tool_name=tool_name,
        event_id=event_id,
        ranges=ranges,
        hinted=hinted,
        inspected=access_type == "read",
        selected=selected,
        ground_truth=gt_key in ground_truth_keys,
        degraded=degraded,
    )
    node_ids.append(function_id)
    return node_ids


def _turn_payload(
    *,
    turn: int,
    base_summary: dict[str, Any],
    tool_call_ids: list[str],
    delta_node_ids: set[str],
    cumulative_node_ids: set[str],
    touched_node_ids: set[str],
    selected_node_ids: set[str],
    hinted_file_count: int,
    candidate_file_count: int,
    inspected_file_count: int,
    selected_file_count: int,
    candidate_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = dict(base_summary)
    summary["hinted_file_count"] = hinted_file_count
    summary["candidate_file_count"] = candidate_file_count
    summary["inspected_file_count"] = inspected_file_count
    summary["selected_file_count"] = selected_file_count
    summary["candidate_groups"] = candidate_groups
    return {
        "turn": turn,
        "tool_call_ids": tool_call_ids,
        "delta_node_ids": sorted(delta_node_ids),
        "cumulative_node_ids": sorted(cumulative_node_ids),
        "touched_node_ids": sorted(touched_node_ids),
        "selected_node_ids": sorted(selected_node_ids),
        "summary": summary,
    }


def _build_from_trace_turns(
    state: _JourneyGraphState,
    case_data: dict[str, Any],
    trace_turns: list[dict[str, Any]],
    *,
    hinted_paths: list[str],
    gt_file_paths: set[str],
    gt_context_paths: set[str],
    gt_function_keys: set[tuple[str, str | None, str, tuple[int, int]]],
) -> list[dict[str, Any]]:
    events = case_data.get("events") if isinstance(case_data.get("events"), list) else []
    events_by_id, events_by_name = _event_groups(events)
    seen_node_ids = {_query_node_id()}
    cumulative_node_ids = {_query_node_id()}
    previous_step_node_id = _query_node_id()
    previous_context_node_ids = [_hint_candidate_set_node_id()] if hinted_paths else []
    first_turn = min(
        (
            entry.get("turn")
            for entry in trace_turns
            if isinstance(entry.get("turn"), int) and entry.get("turn") > 0
        ),
        default=0,
    )
    payloads: list[dict[str, Any]] = []
    hinted_path_set = set(hinted_paths)

    for turn_entry in trace_turns:
        turn = turn_entry.get("turn")
        if not isinstance(turn, int) or turn <= 0:
            continue
        tool_calls_raw = turn_entry.get("tool_calls_raw")
        tool_results = turn_entry.get("tool_results")
        if not isinstance(tool_calls_raw, list):
            tool_calls_raw = []
        if not isinstance(tool_results, list):
            tool_results = []
        tool_results_by_id, unnamed_tool_results_by_name = _tool_result_maps(tool_results)

        turn_tool_call_ids: list[str] = []
        turn_delta_node_ids: set[str] = set()
        turn_touched_node_ids: set[str] = set()
        turn_selected_node_ids: set[str] = set()
        turn_candidate_paths: set[str] = set()
        turn_inspected_paths: set[str] = set()
        turn_selected_paths: set[str] = set()
        turn_candidate_groups: list[dict[str, Any]] = []

        for call_index, tool_call in enumerate(tool_calls_raw):
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict):
                continue
            tool_name = function.get("name") if isinstance(function.get("name"), str) else "unknown"
            args = _parse_tool_args(tool_call)
            tool_result = _find_tool_result(
                tool_call=tool_call,
                tool_name=tool_name,
                tool_results_by_id=tool_results_by_id,
                unnamed_tool_results_by_name=unnamed_tool_results_by_name,
            )
            tool_call_id = tool_call.get("id") if isinstance(tool_call.get("id"), str) else None
            tool_node_id = state.ensure_tool_call(
                turn=turn,
                call_index=call_index,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                args=args,
                is_success=tool_result.get("success") if isinstance(tool_result, dict) else None,
            )
            turn_tool_call_ids.append(tool_node_id)
            turn_touched_node_ids.add(tool_node_id)
            cumulative_node_ids.add(tool_node_id)
            if tool_node_id not in seen_node_ids:
                seen_node_ids.add(tool_node_id)
                turn_delta_node_ids.add(tool_node_id)

            state.ensure_edge(previous_step_node_id, tool_node_id, kind="next_step", turn=turn)
            previous_step_node_id = tool_node_id

            exact_source_ids, temporal_source_ids = _causal_source_ids(
                args,
                previous_context_node_ids,
                state.nodes,
            )
            for source_id in exact_source_ids:
                state.ensure_edge(source_id, tool_node_id, kind="causal_exact", turn=turn)
            for source_id in temporal_source_ids:
                state.ensure_edge(source_id, tool_node_id, kind="causal_temporal", turn=turn)

            tool_events = events_by_id.get((turn, tool_call_id, tool_name))
            if tool_events is None:
                tool_events = events_by_name.get((turn, tool_name), [])

            candidate_paths_by_type: dict[str, list[str]] = {}
            candidate_event_ids_by_type: dict[str, list[str]] = {}
            current_context_node_ids: list[str] = []

            for event_index, event in enumerate(tool_events):
                event_id = event.get("event_id")
                if not isinstance(event_id, str):
                    event_id = f"event:{turn}:{tool_name}:{event_index}"
                access_type = (
                    event.get("access_type") if isinstance(event.get("access_type"), str) else None
                )
                path = event.get("path")
                if not _is_file_path(path) or access_type is None:
                    continue

                if access_type in _CANDIDATE_ACCESS_TYPES:
                    candidate_paths_by_type.setdefault(access_type, []).append(path)
                    candidate_event_ids_by_type.setdefault(access_type, []).append(event_id)
                    turn_candidate_paths.add(path)
                    continue

                if access_type not in _VISIBLE_ARTIFACT_ACCESS_TYPES:
                    continue

                ranges = _event_ranges(event)
                file_id = state.ensure_file(path)
                state.touch_node(
                    file_id,
                    turn=turn,
                    access_type=access_type,
                    tool_name=tool_name,
                    event_id=event_id,
                    ranges=ranges,
                    hinted=path in hinted_path_set,
                    inspected=access_type == "read",
                    selected=access_type == "select",
                    ground_truth=path in gt_file_paths,
                    ground_truth_context=path in gt_context_paths,
                    degraded=False,
                )
                state.ensure_edge(
                    tool_node_id,
                    file_id,
                    kind="selects" if access_type == "select" else "inspects",
                    turn=turn,
                    tool_name=tool_name,
                    access_type=access_type,
                    detail=event.get("tool_query")
                    if isinstance(event.get("tool_query"), str)
                    else event.get("tool_command")
                    if isinstance(event.get("tool_command"), str)
                    else event.get("symbol_name")
                    if isinstance(event.get("symbol_name"), str)
                    else None,
                )
                turn_touched_node_ids.add(file_id)
                cumulative_node_ids.add(file_id)
                current_context_node_ids.append(file_id)
                if file_id not in seen_node_ids:
                    seen_node_ids.add(file_id)
                    turn_delta_node_ids.add(file_id)
                if access_type == "read":
                    turn_inspected_paths.add(path)
                if access_type == "select":
                    turn_selected_paths.add(path)
                    turn_selected_node_ids.add(file_id)

                for function in event.get("functions", []):
                    if not isinstance(function, dict):
                        continue
                    ref = _function_ref_from_runtime(function)
                    if ref is None:
                        continue
                    function_node_ids = _register_function_ref(
                        state,
                        ref=ref,
                        turn=turn,
                        access_type=access_type,
                        tool_name=tool_name,
                        event_id=event_id,
                        hinted=path in hinted_path_set,
                        selected=access_type == "select",
                        ground_truth_keys=gt_function_keys,
                        degraded=False,
                    )
                    for node_id in function_node_ids:
                        state.ensure_edge(
                            tool_node_id,
                            node_id,
                            kind="selects" if access_type == "select" else "inspects",
                            turn=turn,
                            tool_name=tool_name,
                            access_type=access_type,
                        )
                        turn_touched_node_ids.add(node_id)
                        cumulative_node_ids.add(node_id)
                        current_context_node_ids.append(node_id)
                        if node_id not in seen_node_ids:
                            seen_node_ids.add(node_id)
                            turn_delta_node_ids.add(node_id)
                        if access_type == "select":
                            turn_selected_node_ids.add(node_id)

            for access_type, raw_paths in sorted(candidate_paths_by_type.items()):
                paths = _unique_sorted_paths(raw_paths)
                if not paths:
                    continue
                candidate_node_id = state.ensure_candidate_set(
                    turn=turn,
                    call_index=call_index,
                    access_type=access_type,
                    tool_name=tool_name,
                    paths=paths,
                    event_ids=candidate_event_ids_by_type.get(access_type, []),
                    hinted=False,
                    degraded=False,
                )
                state.ensure_edge(
                    tool_node_id,
                    candidate_node_id,
                    kind="produced_candidates",
                    turn=turn,
                    tool_name=tool_name,
                    access_type=access_type,
                )
                turn_touched_node_ids.add(candidate_node_id)
                cumulative_node_ids.add(candidate_node_id)
                current_context_node_ids.append(candidate_node_id)
                if candidate_node_id not in seen_node_ids:
                    seen_node_ids.add(candidate_node_id)
                    turn_delta_node_ids.add(candidate_node_id)
                turn_candidate_groups.append(
                    {
                        "node_id": candidate_node_id,
                        "label": state.nodes[candidate_node_id]["label"],
                        "access_type": access_type,
                        "count": len(paths),
                        "preview_paths": paths[:6],
                    }
                )

            if current_context_node_ids:
                previous_context_node_ids = list(dict.fromkeys(current_context_node_ids))

        payloads.append(
            _turn_payload(
                turn=turn,
                base_summary=_summary_base(turn, turn_entry, case_data),
                tool_call_ids=turn_tool_call_ids,
                delta_node_ids=turn_delta_node_ids,
                cumulative_node_ids=cumulative_node_ids,
                touched_node_ids=turn_touched_node_ids,
                selected_node_ids=turn_selected_node_ids,
                hinted_file_count=len(hinted_paths) if turn == first_turn else 0,
                candidate_file_count=len(turn_candidate_paths),
                inspected_file_count=len(turn_inspected_paths),
                selected_file_count=len(turn_selected_paths),
                candidate_groups=turn_candidate_groups,
            )
        )

    return payloads


def _build_degraded_turns(
    state: _JourneyGraphState,
    case_data: dict[str, Any],
    *,
    hinted_paths: list[str],
    gt_file_paths: set[str],
    gt_context_paths: set[str],
    gt_function_keys: set[tuple[str, str | None, str, tuple[int, int]]],
) -> list[dict[str, Any]]:
    events = [event for event in case_data.get("events", []) if isinstance(event, dict)]
    hinted_path_set = set(hinted_paths)
    turns = sorted(
        {
            event.get("turn")
            for event in events
            if isinstance(event.get("turn"), int) and event.get("turn") > 0
        }
    )
    seen_node_ids = {_query_node_id()}
    cumulative_node_ids = {_query_node_id()}
    payloads: list[dict[str, Any]] = []
    first_turn = turns[0] if turns else 0

    for turn in turns:
        turn_events = [event for event in events if event.get("turn") == turn]
        turn_delta_node_ids: set[str] = set()
        turn_touched_node_ids: set[str] = set()
        turn_selected_node_ids: set[str] = set()
        turn_candidate_paths: set[str] = set()
        turn_inspected_paths: set[str] = set()
        turn_selected_paths: set[str] = set()
        for index, event in enumerate(turn_events):
            access_type = (
                event.get("access_type") if isinstance(event.get("access_type"), str) else None
            )
            path = event.get("path")
            if not _is_file_path(path) or access_type is None:
                continue
            event_id = (
                event.get("event_id")
                if isinstance(event.get("event_id"), str)
                else f"degraded:{turn}:{index}"
            )
            if access_type in _CANDIDATE_ACCESS_TYPES:
                turn_candidate_paths.add(path)
                continue
            if access_type not in _VISIBLE_ARTIFACT_ACCESS_TYPES:
                continue
            file_id = state.ensure_file(path)
            state.touch_node(
                file_id,
                turn=turn,
                access_type=access_type,
                tool_name=event.get("tool_name")
                if isinstance(event.get("tool_name"), str)
                else None,
                event_id=event_id,
                ranges=_event_ranges(event),
                hinted=path in hinted_path_set,
                inspected=access_type == "read",
                selected=access_type == "select",
                ground_truth=path in gt_file_paths,
                ground_truth_context=path in gt_context_paths,
                degraded=True,
            )
            turn_touched_node_ids.add(file_id)
            cumulative_node_ids.add(file_id)
            if file_id not in seen_node_ids:
                seen_node_ids.add(file_id)
                turn_delta_node_ids.add(file_id)
            if access_type == "read":
                turn_inspected_paths.add(path)
            if access_type == "select":
                turn_selected_paths.add(path)
                turn_selected_node_ids.add(file_id)

            for function in event.get("functions", []):
                if not isinstance(function, dict):
                    continue
                ref = _function_ref_from_runtime(function)
                if ref is None:
                    continue
                for node_id in _register_function_ref(
                    state,
                    ref=ref,
                    turn=turn,
                    access_type=access_type,
                    tool_name=event.get("tool_name")
                    if isinstance(event.get("tool_name"), str)
                    else None,
                    event_id=event_id,
                    hinted=path in hinted_path_set,
                    selected=access_type == "select",
                    ground_truth_keys=gt_function_keys,
                    degraded=True,
                ):
                    turn_touched_node_ids.add(node_id)
                    cumulative_node_ids.add(node_id)
                    if node_id not in seen_node_ids:
                        seen_node_ids.add(node_id)
                        turn_delta_node_ids.add(node_id)
                    if access_type == "select":
                        turn_selected_node_ids.add(node_id)

        base_summary = {
            "tool_names": [
                name
                for summary in case_data.get("turn_summaries", [])
                if isinstance(summary, dict) and summary.get("turn") == turn
                for name in summary.get("tool_names", [])
                if isinstance(name, str)
            ],
            "new_files": [
                path
                for summary in case_data.get("turn_summaries", [])
                if isinstance(summary, dict) and summary.get("turn") == turn
                for path in summary.get("new_files", [])
                if isinstance(path, str)
            ],
            "new_functions": [
                item
                for summary in case_data.get("turn_summaries", [])
                if isinstance(summary, dict) and summary.get("turn") == turn
                for item in summary.get("new_functions", [])
                if isinstance(item, dict)
            ],
            "selected_files": [
                path
                for summary in case_data.get("turn_summaries", [])
                if isinstance(summary, dict) and summary.get("turn") == turn
                for path in summary.get("selected_files", [])
                if isinstance(path, str)
            ],
            "llm_latency_ms": next(
                (
                    summary.get("llm_latency_ms")
                    for summary in case_data.get("turn_summaries", [])
                    if isinstance(summary, dict) and summary.get("turn") == turn
                ),
                None,
            ),
            "prompt_tokens": next(
                (
                    summary.get("prompt_tokens")
                    for summary in case_data.get("turn_summaries", [])
                    if isinstance(summary, dict) and summary.get("turn") == turn
                ),
                None,
            ),
            "completion_tokens": next(
                (
                    summary.get("completion_tokens")
                    for summary in case_data.get("turn_summaries", [])
                    if isinstance(summary, dict) and summary.get("turn") == turn
                ),
                None,
            ),
        }
        payloads.append(
            _turn_payload(
                turn=turn,
                base_summary=base_summary,
                tool_call_ids=[],
                delta_node_ids=turn_delta_node_ids,
                cumulative_node_ids=cumulative_node_ids,
                touched_node_ids=turn_touched_node_ids,
                selected_node_ids=turn_selected_node_ids,
                hinted_file_count=len(hinted_paths) if turn == first_turn else 0,
                candidate_file_count=len(turn_candidate_paths),
                inspected_file_count=len(turn_inspected_paths),
                selected_file_count=len(turn_selected_paths),
                candidate_groups=[],
            )
        )

    return payloads


def build_journey_graph(
    case_data: dict[str, Any],
    *,
    trace_turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = _JourneyGraphState()
    query_id = state.ensure_query(
        case_data.get("query") if isinstance(case_data.get("query"), str) else ""
    )
    result_id = state.ensure_result(
        case_data.get("result_status")
        if isinstance(case_data.get("result_status"), str)
        else "result"
    )

    hinted_paths = _unique_sorted_paths(
        [
            item.get("filename")
            for item in case_data.get("semantic_hints", [])
            if isinstance(item, dict)
        ]
    )
    gt_file_paths = {
        path for path in (case_data.get("ground_truth_files") or {}) if _is_file_path(path)
    }
    gt_context_paths = {
        path for path in (case_data.get("ground_truth_context_files") or {}) if _is_file_path(path)
    }
    gt_function_keys = _ground_truth_function_keys(case_data)
    degraded_reasons: list[str] = []

    if hinted_paths:
        hint_node_id = state.ensure_candidate_set(
            turn=None,
            call_index=None,
            access_type=_HINT_ACCESS_TYPE,
            tool_name=None,
            paths=hinted_paths,
            event_ids=[],
            hinted=True,
            degraded=False,
        )
        state.ensure_edge(query_id, hint_node_id, kind="hint")

    trace_turns_list = trace_turns if isinstance(trace_turns, list) else None
    if trace_turns_list:
        turns = _build_from_trace_turns(
            state,
            case_data,
            trace_turns_list,
            hinted_paths=hinted_paths,
            gt_file_paths=gt_file_paths,
            gt_context_paths=gt_context_paths,
            gt_function_keys=gt_function_keys,
        )
    else:
        degraded_reasons.append("trace_turns_missing")
        turns = _build_degraded_turns(
            state,
            case_data,
            hinted_paths=hinted_paths,
            gt_file_paths=gt_file_paths,
            gt_context_paths=gt_context_paths,
            gt_function_keys=gt_function_keys,
        )
        for node in state.nodes.values():
            node["status_flags"]["degraded"] = True

    hinted_path_set = set(hinted_paths)
    selected_node_ids: set[str] = set()
    for path in case_data.get("selected_files") or []:
        if not _is_file_path(path):
            continue
        file_id = state.ensure_file(path)
        state.touch_node(
            file_id,
            turn=None,
            hinted=path in hinted_path_set,
            selected=True,
            ground_truth=path in gt_file_paths,
            ground_truth_context=path in gt_context_paths,
            degraded=bool(degraded_reasons),
        )
        selected_node_ids.add(file_id)

    for item in case_data.get("function_blocks") or []:
        if not isinstance(item, dict):
            continue
        ref = _function_ref_from_runtime(item)
        if ref is None:
            continue
        access_kinds = (
            item.get("access_kinds") if isinstance(item.get("access_kinds"), list) else []
        )
        if not any(kind in {"read", "select"} for kind in access_kinds):
            continue
        for node_id in _register_function_ref(
            state,
            ref=ref,
            turn=item.get("first_turn") if isinstance(item.get("first_turn"), int) else None,
            access_type="select" if "select" in access_kinds else "read",
            tool_name=None,
            event_id=None,
            hinted=ref["path"] in hinted_path_set,
            selected="select" in access_kinds,
            ground_truth_keys=gt_function_keys,
            degraded=bool(degraded_reasons),
        ):
            if "select" in access_kinds:
                selected_node_ids.add(node_id)

    for node_id in sorted(selected_node_ids):
        state.ensure_edge(node_id, result_id, kind="converges", is_final_path=True)

    return {
        "nodes": state.serialize_nodes(),
        "edges": state.serialize_edges(),
        "turns": turns,
        "meta": {
            "mode": "single",
            "default_view": "cumulative",
            "default_layout": "klay",
            "degraded": bool(degraded_reasons),
            "degraded_reasons": degraded_reasons,
            "max_turn": max((turn.get("turn", 0) for turn in turns), default=0),
        },
    }
