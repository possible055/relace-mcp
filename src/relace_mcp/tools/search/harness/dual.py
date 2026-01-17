import asyncio
import logging
from typing import Any

from ....clients import SearchLLMClient
from ....config import RelaceConfig
from .channels import LexicalChannel, SemanticChannel
from .channels.base import ChannelEvidence
from .core import FastAgenticSearchHarness
from .merger import MergerAgent, fallback_union_merge

logger = logging.getLogger(__name__)


class DualChannelHarness:
    """Dual-channel search harness with 3+3+1 parallel merge architecture.

    Runs lexical and semantic search channels in parallel (3 turns each),
    then merges results with a single LLM call.
    """

    def __init__(
        self,
        config: RelaceConfig,
        client: SearchLLMClient,
        *,
        lsp_languages: frozenset[str] | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._lsp_languages = lsp_languages if lsp_languages is not None else frozenset()
        self._dual_mode = bool(self._lsp_languages)

    def run(self, query: str) -> dict[str, Any]:
        """Execute dual-channel search synchronously."""
        if not self._dual_mode:
            logger.info("No LSP languages available, falling back to single harness")
            harness = FastAgenticSearchHarness(
                self._config, self._client, lsp_languages=self._lsp_languages
            )
            return harness.run(query)

        lexical = LexicalChannel(
            self._config, self._client, max_turns=3, lsp_languages=self._lsp_languages
        )
        semantic = SemanticChannel(
            self._config, self._client, max_turns=3, lsp_languages=self._lsp_languages
        )

        lex_result = lexical.run(query)
        sem_result = semantic.run(query)

        if self._config.base_dir is None:
            return fallback_union_merge(query, lex_result, sem_result)
        merger = MergerAgent(self._config, self._client, self._config.base_dir)
        return merger.merge(query, lex_result, sem_result)

    async def run_async(self, query: str) -> dict[str, Any]:
        """Execute dual-channel search asynchronously with parallel channels."""
        if not self._dual_mode:
            logger.info("No LSP languages available, falling back to single harness")
            harness = FastAgenticSearchHarness(
                self._config, self._client, lsp_languages=self._lsp_languages
            )
            return await harness.run_async(query)

        lexical = LexicalChannel(
            self._config, self._client, max_turns=3, lsp_languages=self._lsp_languages
        )
        semantic = SemanticChannel(
            self._config, self._client, max_turns=3, lsp_languages=self._lsp_languages
        )

        results = await asyncio.gather(
            lexical.run_async(query),
            semantic.run_async(query),
            return_exceptions=True,
        )

        lex_result = self._handle_exception(results[0], "lexical")
        sem_result = self._handle_exception(results[1], "semantic")

        if self._config.base_dir is None:
            return fallback_union_merge(query, lex_result, sem_result)
        merger = MergerAgent(self._config, self._client, self._config.base_dir)
        return await merger.merge_async(query, lex_result, sem_result)

    def _handle_exception(
        self, result: ChannelEvidence | BaseException, channel: str
    ) -> ChannelEvidence:
        """Convert exceptions to error ChannelEvidence."""
        if isinstance(result, BaseException):
            logger.error("Channel %s failed with exception: %s", channel, result)
            return ChannelEvidence(
                files={},
                observations=[f"Channel failed: {result}"],
                turns_used=0,
                partial=True,
                error=str(result),
            )
        return result
