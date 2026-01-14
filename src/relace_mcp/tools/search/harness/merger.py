import json
import logging
from typing import Any

from ....clients import SearchLLMClient
from ....config import RelaceConfig
from ....config.settings import MERGER_TEMPERATURE
from .channels.base import ChannelEvidence

logger = logging.getLogger(__name__)

MERGER_SYSTEM_PROMPT = """You are a code search result merger.

You will receive findings from two parallel search channels:
1. Lexical: Text pattern matches (grep, glob)
2. Semantic: Code structure analysis (LSP symbols, call graphs)

Your task:
1. Deduplicate: Remove redundant file ranges that overlap
2. Prioritize: Rank files by relevance to the original query
3. Synthesize: Combine insights from both channels
4. Call the merge_report tool with your final results

Rules:
- Prefer semantic findings when both channels found the same code area
- Include lexical-only findings if they appear relevant
- Use PRECISE line ranges, not entire files
- Merge overlapping ranges within the same file"""

MERGE_REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "merge_report",
        "strict": True,
        "description": "Report the merged search results",
        "parameters": {
            "type": "object",
            "required": ["explanation", "files"],
            "properties": {
                "explanation": {
                    "type": "string",
                    "description": "Summary of findings and reasoning",
                },
                "files": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                    },
                    "description": "File paths to line ranges",
                },
            },
            "additionalProperties": False,
        },
    },
}


class MergerAgent:
    """Single-turn agent that merges evidence from parallel channels."""

    def __init__(self, config: RelaceConfig, client: SearchLLMClient) -> None:
        self._config = config
        self._client = client

    def merge(
        self, query: str, lexical: ChannelEvidence, semantic: ChannelEvidence
    ) -> dict[str, Any]:
        """Merge channel evidence synchronously."""
        trace_id = f"merger-{id(self) % 10000:04d}"
        logger.info("[%s] Starting merge", trace_id)

        if lexical.error and semantic.error:
            return self._fallback_merge(query, lexical, semantic)

        merge_prompt = self._build_merge_prompt(query, lexical, semantic)
        messages = [
            {"role": "system", "content": MERGER_SYSTEM_PROMPT},
            {"role": "user", "content": merge_prompt},
        ]

        try:
            response = self._client.chat(
                messages,
                tools=[MERGE_REPORT_TOOL],
                trace_id=trace_id,
                temperature=MERGER_TEMPERATURE,
            )
            return self._parse_response(query, response, lexical, semantic)
        except Exception as exc:
            logger.exception("[%s] Merge failed", trace_id)
            return self._fallback_merge(query, lexical, semantic, error=str(exc))

    async def merge_async(
        self, query: str, lexical: ChannelEvidence, semantic: ChannelEvidence
    ) -> dict[str, Any]:
        """Merge channel evidence asynchronously."""
        trace_id = f"merger-{id(self) % 10000:04d}"
        logger.info("[%s] Starting async merge", trace_id)

        if lexical.error and semantic.error:
            return self._fallback_merge(query, lexical, semantic)

        merge_prompt = self._build_merge_prompt(query, lexical, semantic)
        messages = [
            {"role": "system", "content": MERGER_SYSTEM_PROMPT},
            {"role": "user", "content": merge_prompt},
        ]

        try:
            response = await self._client.chat_async(
                messages,
                tools=[MERGE_REPORT_TOOL],
                trace_id=trace_id,
                temperature=MERGER_TEMPERATURE,
            )
            return self._parse_response(query, response, lexical, semantic)
        except Exception as exc:
            logger.exception("[%s] Async merge failed", trace_id)
            return self._fallback_merge(query, lexical, semantic, error=str(exc))

    def _build_merge_prompt(
        self, query: str, lexical: ChannelEvidence, semantic: ChannelEvidence
    ) -> str:
        lex_files = json.dumps(lexical.files, indent=2) if lexical.files else "{}"
        sem_files = json.dumps(semantic.files, indent=2) if semantic.files else "{}"
        lex_obs = "\n".join(f"- {o[:200]}" for o in lexical.observations[:3])
        sem_obs = "\n".join(f"- {o[:200]}" for o in semantic.observations[:3])

        return f"""Original query: {query}

## Lexical Channel Results (turns: {lexical.turns_used}, partial: {lexical.partial})
Files found:
{lex_files}

Observations:
{lex_obs or "(none)"}

## Semantic Channel Results (turns: {semantic.turns_used}, partial: {semantic.partial})
Files found:
{sem_files}

Observations:
{sem_obs or "(none)"}

Please merge these findings and call merge_report with the result."""

    def _parse_response(
        self,
        query: str,
        response: dict[str, Any],
        lexical: ChannelEvidence,
        semantic: ChannelEvidence,
    ) -> dict[str, Any]:
        choices = response.get("choices", [])
        if not choices:
            return self._fallback_merge(query, lexical, semantic, error="Empty response")

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            return self._fallback_merge(query, lexical, semantic, error="No tool call")

        for tc in tool_calls:
            func = tc.get("function", {})
            if func.get("name") == "merge_report":
                try:
                    args = json.loads(func.get("arguments", "{}"))
                    return {
                        "query": query,
                        "explanation": args.get("explanation", ""),
                        "files": self._normalize_files(args.get("files", {})),
                        "turns_used": max(lexical.turns_used, semantic.turns_used) + 1,
                        "channels": {
                            "lexical": lexical.turns_used,
                            "semantic": semantic.turns_used,
                        },
                    }
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse merge_report args: %s", exc)

        return self._fallback_merge(query, lexical, semantic, error="Invalid tool call")

    def _fallback_merge(
        self,
        query: str,
        lexical: ChannelEvidence,
        semantic: ChannelEvidence,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Fallback: simple union of files when LLM merge fails."""
        merged_files: dict[str, list[list[int]]] = {}
        for path, ranges in lexical.files.items():
            merged_files.setdefault(path, []).extend(ranges)
        for path, ranges in semantic.files.items():
            merged_files.setdefault(path, []).extend(ranges)

        for path in merged_files:
            merged_files[path] = self._merge_overlapping_ranges(merged_files[path])

        explanation = "[FALLBACK] Merged results from both channels."
        if error:
            explanation = f"[FALLBACK] Merge error: {error}"

        return {
            "query": query,
            "explanation": explanation,
            "files": merged_files,
            "turns_used": max(lexical.turns_used, semantic.turns_used) + 1,
            "partial": True,
            "error": error,
        }

    def _normalize_files(self, files: dict[str, Any]) -> dict[str, list[list[int]]]:
        """Normalize file ranges to list of [start, end] pairs."""
        normalized: dict[str, list[list[int]]] = {}
        for path, ranges in files.items():
            if not isinstance(ranges, list):
                continue
            valid_ranges: list[list[int]] = []
            for r in ranges:
                if isinstance(r, list) and len(r) == 2:
                    try:
                        valid_ranges.append([int(r[0]), int(r[1])])
                    except (ValueError, TypeError):
                        pass
            if valid_ranges:
                normalized[path] = self._merge_overlapping_ranges(valid_ranges)
        return normalized

    def _merge_overlapping_ranges(self, ranges: list[list[int]]) -> list[list[int]]:
        """Merge overlapping or adjacent ranges."""
        if not ranges:
            return []
        sorted_ranges = sorted(ranges, key=lambda x: (x[0], x[1]))
        merged = [list(sorted_ranges[0])]
        for start, end in sorted_ranges[1:]:
            last = merged[-1]
            if start <= last[1] + 1:
                last[1] = max(last[1], end)
            else:
                merged.append([start, end])
        return merged
