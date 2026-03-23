import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from ..analysis.trace_artifacts import (
    TRACE_ARTIFACT_SCHEMA_VERSION,
    ArtifactState,
    build_search_complete_event,
    build_trace_meta_payload,
)
from .experiment_paths import experiment_events_path, experiment_traces_dir


@dataclass(frozen=True)
class ArtifactWriteResult:
    path: str | None
    state: ArtifactState
    warnings: tuple[str, ...] = field(default_factory=tuple)


class BenchmarkTraceRecorder:
    def __init__(
        self,
        *,
        enabled: bool,
        experiment_root: Path,
        run_id: str,
        search_mode: str,
    ):
        self.enabled = enabled
        self.experiment_root = experiment_root
        self.run_id = run_id
        self.search_mode = search_mode
        self.traces_dir: Path | None = None
        self.events_path: Path | None = None
        self._events_file: TextIO | None = None

    def start_run(self) -> None:
        if not self.enabled:
            return

        self.traces_dir = experiment_traces_dir(self.experiment_root)
        self.traces_dir.mkdir(parents=True, exist_ok=True)

        self.events_path = experiment_events_path(self.experiment_root)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.events_path.unlink(missing_ok=True)
        except Exception:
            pass
        self._events_file = self.events_path.open("w", encoding="utf-8")

    def finish_run(self) -> None:
        if self._events_file is None:
            return
        try:
            self._events_file.close()
        finally:
            self._events_file = None

    def artifact_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trace_enabled": self.enabled,
            "schema_version": TRACE_ARTIFACT_SCHEMA_VERSION if self.enabled else None,
            "run_id": self.run_id,
            "experiment_root": str(self.experiment_root),
        }
        if self.enabled and self.traces_dir is not None:
            payload["traces_dir"] = str(self.traces_dir)
        if self.enabled and self.events_path is not None:
            payload["events_path"] = str(self.events_path)
        return payload

    def write_search_start(self, *, case_id: str, repo: str, query: str) -> None:
        if not self.enabled:
            return
        self._emit_event(
            {
                "kind": "search_start",
                "case_id": case_id,
                "repo": repo,
                "search_mode": self.search_mode,
                "query_preview": (query or "")[:500],
            }
        )

    def write_case_trace(
        self,
        *,
        case_id: str,
        turns_log: list[dict[str, Any]] | None,
    ) -> ArtifactWriteResult:
        if not self.enabled:
            return ArtifactWriteResult(path=None, state="disabled")
        if not turns_log:
            return ArtifactWriteResult(path=None, state="missing")
        if self.traces_dir is None:
            raise RuntimeError("Trace recorder not initialized")

        trace_path = self.traces_dir / f"{case_id}.jsonl"
        try:
            with trace_path.open("w", encoding="utf-8") as handle:
                for entry in turns_log:
                    handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            return ArtifactWriteResult(
                path=None,
                state="write_error",
                warnings=(f"trace_jsonl_write_error: {exc}",),
            )
        return ArtifactWriteResult(path=str(trace_path), state="written")

    def write_case_meta(
        self,
        *,
        case_id: str,
        repo: str,
        query: str | None,
        result: dict[str, Any],
    ) -> ArtifactWriteResult:
        if not self.enabled:
            return ArtifactWriteResult(path=None, state="disabled")
        if self.traces_dir is None:
            raise RuntimeError("Trace recorder not initialized")

        meta_path = self.traces_dir / f"{case_id}.meta.json"
        payload = build_trace_meta_payload(
            case_id=case_id,
            repo=repo,
            query=query,
            search_mode=self.search_mode,
            retrieval_backend=result.get("retrieval_backend"),
            retrieval_latency_s=result.get("retrieval_latency_s"),
            hint_policy=result.get("hint_policy"),
            hints_index_freshness=result.get("hints_index_freshness"),
            background_refresh_scheduled=result.get("background_refresh_scheduled"),
            reindex_action=result.get("reindex_action"),
            semantic_hints_used=int(result.get("semantic_hints_used", 0) or 0),
            semantic_hints=result.get("semantic_hints"),
            warnings=result.get("warnings"),
        )
        try:
            with meta_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
        except Exception as exc:
            return ArtifactWriteResult(
                path=None,
                state="write_error",
                warnings=(f"trace_meta_write_error: {exc}",),
            )
        return ArtifactWriteResult(path=str(meta_path), state="written")

    def write_case_events(
        self,
        *,
        case_id: str,
        repo: str,
        benchmark_result: Any,
        result: dict[str, Any],
        turns_log: list[dict[str, Any]] | None,
    ) -> None:
        if not self.enabled:
            return

        base = {
            "case_id": case_id,
            "repo": repo,
            "search_mode": benchmark_result.search_mode,
        }

        if turns_log:
            for entry in turns_log:
                if not isinstance(entry, dict):
                    continue
                turn = entry.get("turn")
                if not isinstance(turn, int) or turn <= 0:
                    continue

                turn_event: dict[str, Any] = {
                    **base,
                    "kind": "search_turn",
                    "turn": turn,
                    "llm_latency_ms": entry.get("llm_latency_ms"),
                }

                llm_response = entry.get("llm_response")
                if isinstance(llm_response, dict):
                    usage = llm_response.get("usage")
                    if isinstance(usage, dict):
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                            value = usage.get(key)
                            if isinstance(value, int):
                                turn_event[key] = value

                self._emit_event(turn_event)

                tool_results = entry.get("tool_results")
                if not isinstance(tool_results, list):
                    continue
                for tool_result in tool_results:
                    if not isinstance(tool_result, dict):
                        continue
                    self._emit_event(
                        {
                            **base,
                            "kind": "tool_call",
                            "turn": turn,
                            "tool_call_id": tool_result.get("id"),
                            "tool_name": tool_result.get("name"),
                            "latency_ms": tool_result.get("latency_ms"),
                            "success": tool_result.get("success"),
                        }
                    )

        self._emit_event(
            build_search_complete_event(
                case_id=case_id,
                repo=repo,
                search_mode=benchmark_result.search_mode,
                turns_used=benchmark_result.turns_used,
                partial=benchmark_result.partial,
                files_found=benchmark_result.returned_files_count,
                total_latency_ms=round(benchmark_result.latency_s * 1000, 1),
                retrieval_backend=benchmark_result.retrieval_backend,
                semantic_hints_used=benchmark_result.hints_used,
                hint_policy=result.get("hint_policy"),
                hints_index_freshness=result.get("hints_index_freshness"),
                background_refresh_scheduled=result.get("background_refresh_scheduled"),
                reindex_action=benchmark_result.reindex_action,
            )
        )
        if benchmark_result.error:
            self._emit_event(
                {
                    **base,
                    "kind": "search_error",
                    "error": benchmark_result.error[:1000],
                }
            )

        if self._events_file is not None:
            try:
                self._events_file.flush()
            except Exception:
                pass

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self._events_file is None:
            return

        payload = dict(event)
        payload.setdefault("timestamp", datetime.now(UTC).isoformat())
        payload.setdefault("run_id", self.run_id)
        payload.setdefault("schema_version", TRACE_ARTIFACT_SCHEMA_VERSION)

        try:
            self._events_file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            return
