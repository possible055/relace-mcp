import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai

from relace_mcp.config import RelaceConfig, create_provider_config
from relace_mcp.config.settings import SEARCH_TEMPERATURE

logger = logging.getLogger(__name__)

SOLVABILITY_PROMPT = """You are evaluating whether a code search system could reasonably locate relevant code files and functions given an issue description.

Criteria for solvability (the issue is solvable if ANY of these apply):
1. Contains specific file paths, function names, class names, or module names
2. Describes a specific error message, exception, or traceback with identifiable code references
3. References specific features, APIs, or components by their technical names
4. Includes code snippets or configuration examples that reveal structure

NOT solvable if ALL of these apply:
- Only describes symptoms without technical context (e.g., "it's slow", "doesn't work")
- Too vague or abstract to pinpoint code location
- Requires external knowledge not derivable from the codebase
- Is purely a feature request without implementation hints

Analyze the following issue and respond in JSON format:
{{
  "solvable": true/false,
  "confidence": 0.0-1.0,
  "evidence": ["keyword1", "keyword2", ...],
  "reject_reason": null or "reason string"
}}

Issue Title: {title}

Issue Body:
{body}
"""


@dataclass
class SolvabilityResult:
    solvable: bool
    confidence: float
    evidence: list[str]
    reject_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "solvable": self.solvable,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reject_reason": self.reject_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SolvabilityResult":
        return cls(
            solvable=bool(data.get("solvable", False)),
            confidence=float(data.get("confidence", 0.0)),
            evidence=list(data.get("evidence", [])),
            reject_reason=data.get("reject_reason"),
        )


class SolvabilityEvaluator:
    def __init__(
        self,
        config: RelaceConfig,
        *,
        cache_dir: Path | None = None,
    ):
        self._provider_config = create_provider_config(
            "SEARCH",
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            default_timeout=60,
            relace_api_key=config.api_key,
        )
        self._client = openai.OpenAI(
            api_key=self._provider_config.api_key,
            base_url=self._provider_config.base_url,
            timeout=self._provider_config.timeout_seconds,
        )
        self._cache_dir = cache_dir
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

    def _load_from_cache(self, cache_key: str) -> SolvabilityResult | None:
        if not self._cache_dir:
            return None
        cache_file = self._cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return SolvabilityResult.from_dict(data)
        except Exception:
            return None

    def _save_to_cache(self, cache_key: str, result: SolvabilityResult) -> None:
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / f"{cache_key}.json"
        try:
            with cache_file.open("w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2)
        except Exception:
            pass

    def evaluate(self, query: str) -> SolvabilityResult:
        cache_key = self._get_cache_key(query)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        lines = query.split("\n", 1)
        title = lines[0].strip() if lines else ""
        body = lines[1].strip() if len(lines) > 1 else ""

        prompt = SOLVABILITY_PROMPT.format(title=title, body=body)

        try:
            response = self._client.chat.completions.create(
                model=self._provider_config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=SEARCH_TEMPERATURE,
                response_format={"type": "json_object"},
                timeout=30.0,  # 30 second timeout per request
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            result = SolvabilityResult(
                solvable=bool(data.get("solvable", False)),
                confidence=float(data.get("confidence", 0.0)),
                evidence=list(data.get("evidence", [])),
                reject_reason=data.get("reject_reason"),
            )
        except openai.APITimeoutError:
            logger.warning("Solvability evaluation timed out")
            result = SolvabilityResult(
                solvable=False,
                confidence=0.0,
                evidence=[],
                reject_reason="Evaluation timed out",
            )
        except openai.AuthenticationError as e:
            logger.error("API key invalid: %s", e)
            result = SolvabilityResult(
                solvable=False,
                confidence=0.0,
                evidence=[],
                reject_reason=f"API auth error: {e}",
            )
        except Exception as e:
            logger.warning("Solvability evaluation failed: %s", e)
            result = SolvabilityResult(
                solvable=False,
                confidence=0.0,
                evidence=[],
                reject_reason=f"Evaluation error: {e}",
            )

        self._save_to_cache(cache_key, result)
        return result

    async def evaluate_async(self, query: str) -> SolvabilityResult:
        cache_key = self._get_cache_key(query)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        lines = query.split("\n", 1)
        title = lines[0].strip() if lines else ""
        body = lines[1].strip() if len(lines) > 1 else ""

        prompt = SOLVABILITY_PROMPT.format(title=title, body=body)

        async_client = openai.AsyncOpenAI(
            api_key=self._provider_config.api_key,
            base_url=self._provider_config.base_url,
            timeout=self._provider_config.timeout_seconds,
        )

        try:
            response = await async_client.chat.completions.create(
                model=self._provider_config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=SEARCH_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            result = SolvabilityResult(
                solvable=bool(data.get("solvable", False)),
                confidence=float(data.get("confidence", 0.0)),
                evidence=list(data.get("evidence", [])),
                reject_reason=data.get("reject_reason"),
            )
        except Exception as e:
            logger.warning("Solvability evaluation failed: %s", e)
            result = SolvabilityResult(
                solvable=False,
                confidence=0.0,
                evidence=[],
                reject_reason=f"Evaluation error: {e}",
            )

        self._save_to_cache(cache_key, result)
        return result
