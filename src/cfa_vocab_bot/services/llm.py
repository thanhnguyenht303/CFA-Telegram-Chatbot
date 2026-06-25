from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class GeneratedVocabContent:
    english_definition: str
    vietnamese_translation: str
    example: str
    exam_trap: str
    confidence_score: float


class LLMContentProvider(Protocol):
    async def generate_vocab_content(
        self, *, term: str, topic: str, source_context: str
    ) -> GeneratedVocabContent | None:
        ...


class NoopLLMProvider:
    """Fallback provider used when no LLM key is configured."""

    async def generate_vocab_content(
        self, *, term: str, topic: str, source_context: str
    ) -> GeneratedVocabContent | None:
        return None


def get_llm_provider(openai_api_key: str | None) -> LLMContentProvider:
    # The MVP deliberately does not require an LLM dependency. A production provider can
    # implement LLMContentProvider and log output through content_generation_log.
    if not openai_api_key:
        return NoopLLMProvider()
    return NoopLLMProvider()

