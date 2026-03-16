import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

TRACE_ARTIFACT_SCHEMA_VERSION = "1.0"
TRACE_META_SUFFIX = ".meta.json"

ArtifactState = Literal["disabled", "written", "missing", "write_error"]


class SemanticHint(TypedDict):
    filename: str
    score: float


class TraceMetaPayload(TypedDict, total=False):
    schema_version: str
    case_id: str
    repo: str
    search_mode: str
    retrieval_backend: str | None
    retrieval_latency_s: float | None
    hint_policy: str | None
    hints_index_freshness: str | None
    background_refresh_scheduled: bool | None
    reindex_action: str | None
    semantic_hints_used: int
    semantic_hints: list[SemanticHint]
    warnings: list[str]


class SearchCompleteEventPayload(TypedDict, total=False):
    kind: Literal["search_complete"]
    case_id: str
    repo: str
    search_mode: str
    turns_used: int
    partial: bool
    files_found: int
    total_latency_ms: float
    retrieval_backend: str | None
    semantic_hints_used: int
    hint_policy: str | None
    hints_index_freshness: str | None
    background_refresh_scheduled: bool | None
    reindex_action: str | None


class ArtifactStatus(TypedDict, total=False):
    trace_jsonl: ArtifactState
    trace_meta: ArtifactState


@dataclass(frozen=True)
class TraceArtifactPaths:
    case_id: str
    trace_path: Path | None = None
    meta_path: Path | None = None


@dataclass
class TraceArtifactValidationResult:
    case_id: str
    valid: bool
    trace_path: str | None = None
    meta_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "valid": self.valid,
            "trace_path": self.trace_path,
            "meta_path": self.meta_path,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class TraceArtifactValidationSummary:
    traces_dir: str
    total_cases: int
    valid_cases: int
    invalid_cases: int
    total_errors: int
    total_warnings: int
    events_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    results: list[TraceArtifactValidationResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "traces_dir": self.traces_dir,
            "events_path": self.events_path,
            "total_cases": self.total_cases,
            "valid_cases": self.valid_cases,
            "invalid_cases": self.invalid_cases,
            "validation_rate": self.valid_cases / self.total_cases if self.total_cases else 0.0,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "errors": self.errors,
            "warnings": self.warnings,
            "results": [result.to_dict() for result in self.results],
        }


def trace_meta_path_for_case(traces_dir: Path, case_id: str) -> Path:
    return traces_dir / f"{case_id}{TRACE_META_SUFFIX}"


def _case_id_from_meta_path(meta_path: Path) -> str:
    name = meta_path.name
    if name.endswith(TRACE_META_SUFFIX):
        return name[: -len(TRACE_META_SUFFIX)]
    return meta_path.stem


def collect_trace_artifacts(traces_dir: Path) -> list[TraceArtifactPaths]:
    cases: dict[str, TraceArtifactPaths] = {}

    for trace_path in sorted(traces_dir.glob("*.jsonl")):
        case_id = trace_path.stem
        existing = cases.get(case_id)
        cases[case_id] = TraceArtifactPaths(
            case_id=case_id,
            trace_path=trace_path,
            meta_path=existing.meta_path if existing else None,
        )

    for meta_path in sorted(traces_dir.glob(f"*{TRACE_META_SUFFIX}")):
        case_id = _case_id_from_meta_path(meta_path)
        existing = cases.get(case_id)
        cases[case_id] = TraceArtifactPaths(
            case_id=case_id,
            trace_path=existing.trace_path if existing else None,
            meta_path=meta_path,
        )

    return [cases[case_id] for case_id in sorted(cases)]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_semantic_hints(raw_hints: Any) -> list[SemanticHint]:
    if not isinstance(raw_hints, list):
        return []

    hints: list[SemanticHint] = []
    for item in raw_hints:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            continue
        score = _safe_float(item.get("score"))
        hints.append({"filename": filename, "score": score if score is not None else 0.0})
    return hints


def normalize_trace_meta(data: Any) -> TraceMetaPayload:
    if not isinstance(data, dict):
        return {}

    payload: TraceMetaPayload = {}

    for key in ("schema_version", "case_id", "repo", "search_mode", "retrieval_backend"):
        value = data.get(key)
        if isinstance(value, str):
            payload[key] = value
        elif value is None and key == "retrieval_backend":
            payload[key] = None

    for key in ("hint_policy", "hints_index_freshness", "reindex_action"):
        value = data.get(key)
        if isinstance(value, str):
            payload[key] = value
        elif value is None:
            payload[key] = None

    retrieval_latency = _safe_float(data.get("retrieval_latency_s"))
    if retrieval_latency is not None:
        payload["retrieval_latency_s"] = retrieval_latency
    elif data.get("retrieval_latency_s") is None:
        payload["retrieval_latency_s"] = None

    background_refresh_scheduled = data.get("background_refresh_scheduled")
    if isinstance(background_refresh_scheduled, bool):
        payload["background_refresh_scheduled"] = background_refresh_scheduled
    elif background_refresh_scheduled is None:
        payload["background_refresh_scheduled"] = None

    semantic_hints = normalize_semantic_hints(data.get("semantic_hints"))
    payload["semantic_hints"] = semantic_hints
    try:
        payload["semantic_hints_used"] = int(data.get("semantic_hints_used", 0) or 0)
    except (TypeError, ValueError):
        payload["semantic_hints_used"] = 0

    warnings = data.get("warnings")
    if isinstance(warnings, list):
        payload["warnings"] = [warning for warning in warnings if isinstance(warning, str)]

    return payload


def load_trace_meta(meta_path: Path | None) -> tuple[TraceMetaPayload, list[str]]:
    if meta_path is None:
        return {}, []
    if not meta_path.exists():
        return {}, [f"Missing trace metadata: {meta_path}"]

    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, [f"Unable to read trace metadata {meta_path}: {exc}"]
    except json.JSONDecodeError as exc:
        return {}, [f"Invalid JSON in trace metadata {meta_path}: {exc}"]

    if not isinstance(data, dict):
        return {}, [f"Trace metadata must be a JSON object: {meta_path}"]
    return normalize_trace_meta(data), []


def load_trace_turns(trace_path: Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    if trace_path is None:
        return [], []
    if not trace_path.exists():
        return [], [f"Missing trace JSONL: {trace_path}"]

    turns: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        with trace_path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    errors.append(f"Invalid JSON in {trace_path}:{lineno}: {exc}")
                    continue
                if not isinstance(entry, dict):
                    errors.append(f"Trace entry must be an object in {trace_path}:{lineno}")
                    continue
                turns.append(entry)
    except OSError as exc:
        errors.append(f"Unable to read trace JSONL {trace_path}: {exc}")

    return turns, errors


def build_trace_meta_payload(
    *,
    case_id: str,
    repo: str,
    search_mode: str,
    retrieval_backend: str | None,
    retrieval_latency_s: float | None,
    hint_policy: str | None,
    hints_index_freshness: str | None,
    background_refresh_scheduled: bool | None,
    reindex_action: str | None,
    semantic_hints_used: int,
    semantic_hints: Any,
    warnings: Any = None,
) -> TraceMetaPayload:
    retrieval_latency = _safe_float(retrieval_latency_s)
    payload: TraceMetaPayload = {
        "schema_version": TRACE_ARTIFACT_SCHEMA_VERSION,
        "case_id": case_id,
        "repo": repo,
        "search_mode": search_mode,
        "retrieval_backend": retrieval_backend,
        "retrieval_latency_s": retrieval_latency,
        "hint_policy": hint_policy,
        "hints_index_freshness": hints_index_freshness,
        "background_refresh_scheduled": background_refresh_scheduled,
        "reindex_action": reindex_action,
        "semantic_hints_used": int(semantic_hints_used),
        "semantic_hints": normalize_semantic_hints(semantic_hints),
    }
    if isinstance(warnings, list):
        filtered = [warning for warning in warnings if isinstance(warning, str)]
        if filtered:
            payload["warnings"] = filtered
    return payload


def build_search_complete_event(
    *,
    case_id: str,
    repo: str,
    search_mode: str,
    turns_used: int,
    partial: bool,
    files_found: int,
    total_latency_ms: float,
    retrieval_backend: str | None,
    semantic_hints_used: int,
    hint_policy: str | None,
    hints_index_freshness: str | None,
    background_refresh_scheduled: bool | None,
    reindex_action: str | None,
) -> SearchCompleteEventPayload:
    return {
        "kind": "search_complete",
        "case_id": case_id,
        "repo": repo,
        "search_mode": search_mode,
        "turns_used": int(turns_used),
        "partial": partial,
        "files_found": int(files_found),
        "total_latency_ms": _safe_float(total_latency_ms) or 0.0,
        "retrieval_backend": retrieval_backend,
        "semantic_hints_used": int(semantic_hints_used),
        "hint_policy": hint_policy,
        "hints_index_freshness": hints_index_freshness,
        "background_refresh_scheduled": background_refresh_scheduled,
        "reindex_action": reindex_action,
    }


def infer_events_path(traces_dir: Path) -> Path | None:
    parent = traces_dir.parent
    if parent.name != "traces":
        return None
    return parent.parent / "events" / f"{traces_dir.name}.jsonl"


def _validate_trace_turns(case_id: str, turns: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    seen_turns: set[int] = set()
    last_turn = 0
    for index, entry in enumerate(turns, 1):
        turn = entry.get("turn")
        if not isinstance(turn, int) or turn <= 0:
            errors.append(f"{case_id}: trace turn {index} has invalid turn number {turn!r}")
            continue
        if turn in seen_turns:
            errors.append(f"{case_id}: duplicate trace turn {turn}")
        seen_turns.add(turn)
        if turn < last_turn:
            warnings.append(f"{case_id}: trace turns are not ordered ({last_turn} -> {turn})")
        last_turn = turn
    return errors, warnings


def _validate_trace_meta_payload(
    case_id: str,
    meta: TraceMetaPayload,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    schema_version = meta.get("schema_version")
    if schema_version != TRACE_ARTIFACT_SCHEMA_VERSION:
        warnings.append(
            f"{case_id}: trace metadata schema_version={schema_version!r} "
            f"(expected {TRACE_ARTIFACT_SCHEMA_VERSION!r})"
        )

    meta_case_id = meta.get("case_id")
    if meta_case_id != case_id:
        errors.append(f"{case_id}: meta case_id mismatch ({meta_case_id!r})")

    search_mode = meta.get("search_mode")
    if search_mode not in {"agentic", "indexed"}:
        errors.append(f"{case_id}: invalid search_mode {search_mode!r}")

    semantic_hints = meta.get("semantic_hints", [])
    semantic_hints_used = meta.get("semantic_hints_used", 0)
    if semantic_hints_used != len(semantic_hints):
        errors.append(
            f"{case_id}: semantic_hints_used={semantic_hints_used} does not match "
            f"{len(semantic_hints)} semantic_hints"
        )

    if search_mode == "agentic" and semantic_hints:
        errors.append(f"{case_id}: agentic trace metadata must not include semantic_hints")

    warnings_list = meta.get("warnings")
    if warnings_list is not None and not isinstance(warnings_list, list):
        errors.append(f"{case_id}: warnings must be a list[str]")

    return errors, warnings


def _read_event_lines(events_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        with events_path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    errors.append(f"Invalid JSON in {events_path}:{lineno}: {exc}")
                    continue
                if not isinstance(entry, dict):
                    errors.append(f"Event entry must be an object in {events_path}:{lineno}")
                    continue
                events.append(entry)
    except OSError as exc:
        errors.append(f"Unable to read events file {events_path}: {exc}")

    return events, errors


def validate_trace_run(
    traces_dir: Path,
    *,
    events_path: Path | None = None,
) -> TraceArtifactValidationSummary:
    artifacts = collect_trace_artifacts(traces_dir)
    results: list[TraceArtifactValidationResult] = []
    run_errors: list[str] = []
    run_warnings: list[str] = []

    for artifact in artifacts:
        turns, turn_load_errors = load_trace_turns(artifact.trace_path)
        meta, meta_load_errors = load_trace_meta(artifact.meta_path)

        errors = list(turn_load_errors) + list(meta_load_errors)
        warnings: list[str] = []

        if artifact.trace_path is None:
            warnings.append(f"{artifact.case_id}: trace JSONL missing; metadata-only case")
        if artifact.meta_path is None:
            warnings.append(
                f"{artifact.case_id}: trace metadata missing; search_map falls back to empty meta"
            )

        turn_errors, turn_warnings = _validate_trace_turns(artifact.case_id, turns)
        errors.extend(turn_errors)
        warnings.extend(turn_warnings)

        if meta:
            meta_errors, meta_warnings = _validate_trace_meta_payload(artifact.case_id, meta)
            errors.extend(meta_errors)
            warnings.extend(meta_warnings)

        results.append(
            TraceArtifactValidationResult(
                case_id=artifact.case_id,
                valid=not errors,
                trace_path=str(artifact.trace_path) if artifact.trace_path else None,
                meta_path=str(artifact.meta_path) if artifact.meta_path else None,
                errors=errors,
                warnings=warnings,
            )
        )

    resolved_events_path = events_path if events_path is not None else infer_events_path(traces_dir)
    if resolved_events_path is not None:
        if not resolved_events_path.exists():
            run_warnings.append(f"Events file not found: {resolved_events_path}")
        else:
            events, event_errors = _read_event_lines(resolved_events_path)
            run_errors.extend(event_errors)

            search_complete_by_case: dict[str, dict[str, Any]] = {}
            for event in events:
                kind = event.get("kind")
                if not isinstance(kind, str):
                    run_errors.append("Encountered event without string kind")
                    continue
                schema_version = event.get("schema_version")
                if schema_version != TRACE_ARTIFACT_SCHEMA_VERSION:
                    run_warnings.append(
                        f"Event schema_version={schema_version!r} "
                        f"(expected {TRACE_ARTIFACT_SCHEMA_VERSION!r})"
                    )
                if kind != "search_complete":
                    continue

                case_id = event.get("case_id")
                if not isinstance(case_id, str) or not case_id:
                    run_errors.append("search_complete event missing case_id")
                    continue
                if case_id in search_complete_by_case:
                    run_errors.append(f"Duplicate search_complete event for case {case_id}")
                    continue
                search_complete_by_case[case_id] = event

            result_by_case = {result.case_id: result for result in results}
            for case_id, result in result_by_case.items():
                event = search_complete_by_case.get(case_id)
                if event is None:
                    run_warnings.append(f"Missing search_complete event for case {case_id}")
                    continue

                meta, _ = load_trace_meta(Path(result.meta_path) if result.meta_path else None)
                if not meta:
                    continue
                if event.get("search_mode") != meta.get("search_mode"):
                    result.errors.append(
                        f"{case_id}: search_complete search_mode mismatch ({event.get('search_mode')!r})"
                    )
                if event.get("retrieval_backend") != meta.get("retrieval_backend"):
                    result.errors.append(
                        f"{case_id}: retrieval_backend mismatch between meta and events"
                    )
                if int(event.get("semantic_hints_used", 0) or 0) != meta.get(
                    "semantic_hints_used", 0
                ):
                    result.errors.append(
                        f"{case_id}: semantic_hints_used mismatch between meta and events"
                    )
                if event.get("hint_policy") != meta.get("hint_policy"):
                    result.errors.append(f"{case_id}: hint_policy mismatch between meta and events")
                if event.get("hints_index_freshness") != meta.get("hints_index_freshness"):
                    result.errors.append(
                        f"{case_id}: hints_index_freshness mismatch between meta and events"
                    )
                if event.get("background_refresh_scheduled") != meta.get(
                    "background_refresh_scheduled"
                ):
                    result.errors.append(
                        f"{case_id}: background_refresh_scheduled mismatch between meta and events"
                    )
                if event.get("reindex_action") != meta.get("reindex_action"):
                    result.errors.append(
                        f"{case_id}: reindex_action mismatch between meta and events"
                    )
                result.valid = not result.errors

    invalid_cases = sum(1 for result in results if not result.valid)
    total_errors = len(run_errors) + sum(len(result.errors) for result in results)
    total_warnings = len(run_warnings) + sum(len(result.warnings) for result in results)
    return TraceArtifactValidationSummary(
        traces_dir=str(traces_dir),
        events_path=str(resolved_events_path) if resolved_events_path is not None else None,
        total_cases=len(results),
        valid_cases=len(results) - invalid_cases,
        invalid_cases=invalid_cases,
        total_errors=total_errors,
        total_warnings=total_warnings,
        errors=run_errors,
        warnings=run_warnings,
        results=results,
    )


def format_trace_validation_report(summary: TraceArtifactValidationSummary) -> str:
    lines = [
        "=" * 60,
        "Trace Artifact Validation",
        "=" * 60,
        f"Traces dir: {summary.traces_dir}",
    ]
    if summary.events_path:
        lines.append(f"Events file: {summary.events_path}")
    lines.extend(
        [
            f"Cases validated: {summary.total_cases}",
            f"Valid cases: {summary.valid_cases}",
            f"Invalid cases: {summary.invalid_cases}",
            f"Total errors: {summary.total_errors}",
            f"Total warnings: {summary.total_warnings}",
        ]
    )

    if summary.errors:
        lines.append("")
        lines.append("Run errors:")
        for error in summary.errors:
            lines.append(f"  - {error}")

    if summary.warnings:
        lines.append("")
        lines.append("Run warnings:")
        for warning in summary.warnings:
            lines.append(f"  - {warning}")

    if summary.results:
        lines.append("")
        lines.append("Per-case results:")
        for result in summary.results:
            status = "OK" if result.valid else "INVALID"
            lines.append(f"  - {result.case_id}: {status}")
            for error in result.errors:
                lines.append(f"      error: {error}")
            for warning in result.warnings:
                lines.append(f"      warning: {warning}")

    return "\n".join(lines)
