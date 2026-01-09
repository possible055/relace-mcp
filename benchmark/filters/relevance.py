"""LLM-based context relevance evaluation.

Uses LLM to judge whether candidate functions are relevant to a given issue,
filtering out noise from the call graph expansion.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import openai

from relace_mcp.config import RelaceConfig, create_provider_config
from relace_mcp.config.settings import SEARCH_TEMPERATURE

from .blacklist import is_blacklisted

if TYPE_CHECKING:
    from ..analysis.call_graph import GlobalFunctionDef

logger = logging.getLogger(__name__)

RELEVANCE_PROMPT = """You are evaluating whether functions from a codebase are relevant to understanding or solving a given issue.

Rate each function's relevance on a scale of 0.0 to 1.0:
- 1.0: Directly mentioned in the issue (by name, class, or clear reference)
- 0.8: Strongly related - called by or calls the modified function, semantically connected
- 0.6: Moderately related - in the same module/feature area, provides useful context
- 0.4: Weakly related - might be useful background context
- 0.2: Tangentially related - shares some keywords but likely not needed
- 0.0: Unrelated - utility function, logging, stdlib wrapper, different feature

Issue:
{query}

Functions to evaluate:
{functions_text}

Respond in JSON format:
{{
  "evaluations": [
    {{"function": "function_name", "score": 0.8, "reason": "brief reason"}}
  ]
}}
"""


@dataclass
class RelevanceResult:
    function_name: str
    file_path: str
    relevance_score: float
    reasoning: str
    include: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function_name,
            "file_path": self.file_path,
            "relevance_score": self.relevance_score,
            "relevance_reason": self.reasoning,
            "include": self.include,
        }


class ContextRelevanceEvaluator:
    """Evaluates relevance of candidate functions to an issue using LLM."""

    def __init__(
        self,
        config: RelaceConfig,
        *,
        threshold: float = 0.5,
        cache_dir: Path | None = None,
        use_heuristic_fallback: bool = True,
    ):
        self._provider_config = create_provider_config(
            "SEARCH",
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            default_timeout=60,
            relace_api_key=config.api_key,
        )
        self._has_api_key = bool(self._provider_config.api_key)
        self._client = (
            openai.OpenAI(
                api_key=self._provider_config.api_key or "dummy",
                base_url=self._provider_config.base_url,
                timeout=self._provider_config.timeout_seconds,
            )
            if self._has_api_key
            else None
        )
        self._threshold = threshold
        self._cache_dir = cache_dir
        self._use_heuristic_fallback = use_heuristic_fallback
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, query: str, func_names: list[str]) -> str:
        combined = query + "|" + ",".join(sorted(func_names))
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

    def _load_from_cache(self, cache_key: str) -> list[RelevanceResult] | None:
        if not self._cache_dir:
            return None
        cache_file = self._cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                RelevanceResult(
                    function_name=r["function"],
                    file_path=r["file_path"],
                    relevance_score=r["relevance_score"],
                    reasoning=r["relevance_reason"],
                    include=r["include"],
                )
                for r in data
            ]
        except Exception:
            return None

    def _save_to_cache(self, cache_key: str, results: list[RelevanceResult]) -> None:
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / f"{cache_key}.json"
        try:
            with cache_file.open("w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in results], f, indent=2)
        except Exception:
            pass

    def _evaluate_heuristic(
        self,
        query: str,
        candidates: list["GlobalFunctionDef"],
    ) -> list[RelevanceResult]:
        """Heuristic fallback when LLM is not available.

        Scores based on:
        - Function name appears in query: +0.5
        - File path appears in query: +0.3
        - Same file as a mentioned function: +0.2
        """
        query_lower = query.lower()
        results: list[RelevanceResult] = []

        for func in candidates:
            score = 0.6  # Base score for being in call graph

            # Check if function name appears in query
            if func.name.lower() in query_lower:
                score += 0.3

            # Check if file path appears in query
            if func.file_path.lower() in query_lower:
                score += 0.2

            # Check if class name appears in query
            if func.class_name and func.class_name.lower() in query_lower:
                score += 0.2

            # Cap at 1.0
            score = min(score, 1.0)

            results.append(
                RelevanceResult(
                    function_name=func.name,
                    file_path=func.file_path,
                    relevance_score=score,
                    reasoning="Heuristic: in call graph"
                    + (", name in query" if func.name.lower() in query_lower else ""),
                    include=score >= self._threshold,
                )
            )

        return results

    def evaluate(
        self,
        query: str,
        candidates: list["GlobalFunctionDef"],
        *,
        batch_size: int = 10,
    ) -> list[RelevanceResult]:
        """Evaluate relevance of candidate functions to the query.

        Args:
            query: The issue text.
            candidates: List of candidate functions from call graph.
            batch_size: Number of functions to evaluate per LLM call.

        Returns:
            List of RelevanceResult for each candidate.
        """
        # Pre-filter blacklisted functions
        filtered_candidates = [c for c in candidates if not is_blacklisted(c.name)]

        if not filtered_candidates:
            return []

        # Check cache
        func_names = [c.name for c in filtered_candidates]
        cache_key = self._get_cache_key(query, func_names)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        # Use heuristic fallback if no API key
        if not self._has_api_key and self._use_heuristic_fallback:
            all_results = self._evaluate_heuristic(query, filtered_candidates)
            self._save_to_cache(cache_key, all_results)
            return all_results

        # Process in batches
        all_results: list[RelevanceResult] = []

        for i in range(0, len(filtered_candidates), batch_size):
            batch = filtered_candidates[i : i + batch_size]
            batch_results = self._evaluate_batch(query, batch)
            all_results.extend(batch_results)

        self._save_to_cache(cache_key, all_results)
        return all_results

    def _evaluate_batch(
        self,
        query: str,
        candidates: list["GlobalFunctionDef"],
    ) -> list[RelevanceResult]:
        """Evaluate a batch of candidates."""
        # Build functions text
        functions_text_parts: list[str] = []
        for i, func in enumerate(candidates, 1):
            class_info = f" (in class {func.class_name})" if func.class_name else ""
            functions_text_parts.append(
                f"{i}. {func.name}{class_info} in {func.file_path}\n"
                f"   Signature: {func.signature}\n"
                f"   Calls: {', '.join(func.calls[:5])}{'...' if len(func.calls) > 5 else ''}"
            )

        functions_text = "\n".join(functions_text_parts)
        prompt = RELEVANCE_PROMPT.format(query=query[:2000], functions_text=functions_text)

        results: list[RelevanceResult] = []

        try:
            response = self._client.chat.completions.create(
                model=self._provider_config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=SEARCH_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            evaluations = data.get("evaluations", [])
            eval_map = {e["function"]: e for e in evaluations if isinstance(e, dict)}

            for func in candidates:
                eval_data = eval_map.get(func.name, {})
                score = float(eval_data.get("score", 0.0))
                reason = str(eval_data.get("reason", "No evaluation"))

                results.append(
                    RelevanceResult(
                        function_name=func.name,
                        file_path=func.file_path,
                        relevance_score=score,
                        reasoning=reason,
                        include=score >= self._threshold,
                    )
                )

        except Exception as e:
            logger.warning("Relevance evaluation failed: %s", e)
            # Return all candidates with low score on error
            for func in candidates:
                results.append(
                    RelevanceResult(
                        function_name=func.name,
                        file_path=func.file_path,
                        relevance_score=0.0,
                        reasoning=f"Evaluation error: {e}",
                        include=False,
                    )
                )

        return results

    async def evaluate_async(
        self,
        query: str,
        candidates: list["GlobalFunctionDef"],
        *,
        batch_size: int = 10,
    ) -> list[RelevanceResult]:
        """Async version of evaluate."""
        # Pre-filter blacklisted functions
        filtered_candidates = [c for c in candidates if not is_blacklisted(c.name)]

        if not filtered_candidates:
            return []

        # Check cache
        func_names = [c.name for c in filtered_candidates]
        cache_key = self._get_cache_key(query, func_names)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        async_client = openai.AsyncOpenAI(
            api_key=self._provider_config.api_key,
            base_url=self._provider_config.base_url,
            timeout=self._provider_config.timeout_seconds,
        )

        all_results: list[RelevanceResult] = []

        for i in range(0, len(filtered_candidates), batch_size):
            batch = filtered_candidates[i : i + batch_size]
            batch_results = await self._evaluate_batch_async(query, batch, async_client)
            all_results.extend(batch_results)

        self._save_to_cache(cache_key, all_results)
        return all_results

    async def _evaluate_batch_async(
        self,
        query: str,
        candidates: list["GlobalFunctionDef"],
        client: openai.AsyncOpenAI,
    ) -> list[RelevanceResult]:
        """Async batch evaluation."""
        functions_text_parts: list[str] = []
        for i, func in enumerate(candidates, 1):
            class_info = f" (in class {func.class_name})" if func.class_name else ""
            functions_text_parts.append(
                f"{i}. {func.name}{class_info} in {func.file_path}\n"
                f"   Signature: {func.signature}\n"
                f"   Calls: {', '.join(func.calls[:5])}{'...' if len(func.calls) > 5 else ''}"
            )

        functions_text = "\n".join(functions_text_parts)
        prompt = RELEVANCE_PROMPT.format(query=query[:2000], functions_text=functions_text)

        results: list[RelevanceResult] = []

        try:
            response = await client.chat.completions.create(
                model=self._provider_config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=SEARCH_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            evaluations = data.get("evaluations", [])
            eval_map = {e["function"]: e for e in evaluations if isinstance(e, dict)}

            for func in candidates:
                eval_data = eval_map.get(func.name, {})
                score = float(eval_data.get("score", 0.0))
                reason = str(eval_data.get("reason", "No evaluation"))

                results.append(
                    RelevanceResult(
                        function_name=func.name,
                        file_path=func.file_path,
                        relevance_score=score,
                        reasoning=reason,
                        include=score >= self._threshold,
                    )
                )

        except Exception as e:
            logger.warning("Relevance evaluation failed: %s", e)
            for func in candidates:
                results.append(
                    RelevanceResult(
                        function_name=func.name,
                        file_path=func.file_path,
                        relevance_score=0.0,
                        reasoning=f"Evaluation error: {e}",
                        include=False,
                    )
                )

        return results
