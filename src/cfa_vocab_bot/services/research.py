from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from cfa_vocab_bot.config import Settings
from cfa_vocab_bot.models import (
    ContentGenerationLog,
    ResearchSuggestion,
    User,
    VocabAlias,
    VocabItem,
    VocabSource,
    utc_now,
)
from cfa_vocab_bot.schemas import ResearchCandidate
from cfa_vocab_bot.services.duplicate import find_duplicate, normalize_term

logger = logging.getLogger(__name__)

MAX_RESEARCH_NUMBER = 25
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class ResearchUnavailable(RuntimeError):
    pass


class ResearchProvider(Protocol):
    async def research(self, *, topic: str, number: int) -> list[ResearchCandidate]:
        ...


def _research_schema() -> dict[str, Any]:
    source_schema = {
        "type": "object",
        "properties": {
            "source_name": {"type": "string"},
            "source_type": {"type": "string"},
            "source_reference": {"type": ["string", "null"]},
            "url": {"type": ["string", "null"]},
        },
        "required": ["source_name", "source_type", "source_reference", "url"],
        "additionalProperties": False,
    }
    candidate_schema = {
        "type": "object",
        "properties": {
            "term": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "topic": {"type": "string"},
            "subtopic": {"type": ["string", "null"]},
            "english_definition": {"type": "string"},
            "vietnamese_translation": {"type": "string"},
            "example": {"type": "string"},
            "exam_trap": {"type": ["string", "null"]},
            "tags": {"type": "array", "items": {"type": "string"}},
            "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            "priority_score": {"type": "number"},
            "sources": {"type": "array", "items": source_schema},
            "research_reason": {"type": ["string", "null"]},
        },
        "required": [
            "term",
            "aliases",
            "topic",
            "subtopic",
            "english_definition",
            "vietnamese_translation",
            "example",
            "exam_trap",
            "tags",
            "difficulty",
            "priority_score",
            "sources",
            "research_reason",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": candidate_schema,
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    }


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks)


class OpenAIWebResearchProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-5.4-mini",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def research(self, *, topic: str, number: int) -> list[ResearchCandidate]:
        if not self.api_key:
            raise ResearchUnavailable("OPENAI_API_KEY is not configured.")

        requested = min(max(number * 2, number), MAX_RESEARCH_NUMBER * 2)
        instructions = (
            "You are a CFA Level I vocabulary research assistant. Search the public web broadly "
            "for CFA Level I-relevant vocabulary and phrases. Prioritize official CFA Institute "
            "public pages, public sample/question guidance, reputable public financial education "
            "sources, and common exam-stem phrases. Do not copy paid or copyrighted explanations "
            "verbatim. Return rewritten original definitions, short Vietnamese translations, CFA-style "
            "examples, exam traps, and source tracking. Avoid terms that are too generic unless they "
            "have a specific CFA Level I exam meaning."
        )
        input_text = (
            f"Research CFA Level I vocabulary for topic: {topic}.\n"
            f"Return the top {requested} candidate terms or phrases. Rank by topic relevance, "
            "exam usefulness, difficulty/trap value, and practical value when reading English CFA "
            "question stems."
        )
        body = {
            "model": self.model,
            "store": False,
            "instructions": instructions,
            "input": input_text,
            "tools": [{"type": "web_search"}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "cfa_vocab_research",
                    "strict": True,
                    "schema": _research_schema(),
                }
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if response.status_code >= 400:
            error_message = f"HTTP {response.status_code}"
            try:
                error_payload = response.json().get("error", {})
                code = error_payload.get("code") or error_payload.get("type")
                message = error_payload.get("message")
                if code or message:
                    error_message = f"{code or response.status_code}: {message or 'OpenAI request failed'}"
            except ValueError:
                pass
            logger.warning("OpenAI research request failed: %s", error_message)
            raise ResearchUnavailable(f"OpenAI research request failed: {error_message}")

        payload = response.json()
        output_text = _extract_output_text(payload)
        if not output_text:
            raise ResearchUnavailable("OpenAI returned no structured output text.")
        try:
            parsed = json.loads(output_text)
            return [ResearchCandidate.model_validate(item) for item in parsed.get("candidates", [])]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ResearchUnavailable("OpenAI returned research output that did not match the schema.") from exc


def provider_from_settings(settings: Settings) -> ResearchProvider:
    return OpenAIWebResearchProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_research_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )


def _already_pending(session: Session, user: User, normalized_term: str, topic: str) -> bool:
    return (
        session.scalar(
            select(ResearchSuggestion).where(
                ResearchSuggestion.user_id == user.id,
                ResearchSuggestion.normalized_term == normalized_term,
                ResearchSuggestion.topic == topic,
                ResearchSuggestion.status == "suggested",
            )
        )
        is not None
    )


def store_research_candidates(
    session: Session,
    *,
    user: User,
    topic: str,
    requested_number: int,
    candidates: Sequence[ResearchCandidate],
    model_name: str | None = None,
) -> list[ResearchSuggestion]:
    suggestions: list[ResearchSuggestion] = []
    raw_output = {"topic": topic, "requested_number": requested_number, "candidates": []}

    for candidate in candidates:
        if len(suggestions) >= requested_number:
            break
        normalized = normalize_term(candidate.term)
        candidate_topic = candidate.topic or topic
        raw_output["candidates"].append(candidate.model_dump())
        if find_duplicate(session, candidate.term, candidate_topic) is not None:
            continue
        if _already_pending(session, user, normalized, candidate_topic):
            continue
        suggestion = ResearchSuggestion(
            user_id=user.id,
            topic=candidate_topic,
            subtopic=candidate.subtopic,
            term=candidate.term,
            normalized_term=normalized,
            aliases=candidate.aliases,
            english_definition=candidate.english_definition,
            vietnamese_translation=candidate.vietnamese_translation,
            example=candidate.example,
            exam_trap=candidate.exam_trap,
            tags=candidate.tags,
            difficulty=candidate.difficulty,
            priority_score=candidate.priority_score,
            sources=[source.model_dump() for source in candidate.sources],
            research_reason=candidate.research_reason,
            raw_payload=candidate.model_dump(),
            status="suggested",
        )
        session.add(suggestion)
        suggestions.append(suggestion)

    session.add(
        ContentGenerationLog(
            prompt_version="research_v1",
            model_name=model_name,
            source_context=f"OpenAI web research topic={topic}",
            generated_output=json.dumps(raw_output, ensure_ascii=False),
            qa_status="suggested",
        )
    )
    session.flush()
    return suggestions


async def research_topic(
    session: Session,
    *,
    user: User,
    topic: str,
    number: int,
    provider: ResearchProvider,
    model_name: str | None = None,
) -> list[ResearchSuggestion]:
    safe_number = min(max(number, 1), MAX_RESEARCH_NUMBER)
    candidates = await provider.research(topic=topic, number=safe_number)
    return store_research_candidates(
        session,
        user=user,
        topic=topic,
        requested_number=safe_number,
        candidates=candidates,
        model_name=model_name,
    )


def approve_research_suggestion(
    session: Session,
    *,
    user: User,
    suggestion_id: int,
) -> tuple[ResearchSuggestion, VocabItem | None, str]:
    suggestion = session.get(ResearchSuggestion, suggestion_id)
    if suggestion is None or suggestion.user_id != user.id:
        raise ValueError("Research suggestion not found.")
    if suggestion.status == "approved" and suggestion.vocab_id:
        return suggestion, session.get(VocabItem, suggestion.vocab_id), "already_approved"
    if suggestion.status not in {"suggested", "duplicate"}:
        return suggestion, None, suggestion.status

    duplicate = find_duplicate(session, suggestion.term, suggestion.topic)
    if duplicate:
        suggestion.status = "duplicate"
        return suggestion, duplicate, "duplicate"

    vocab = VocabItem(
        term=suggestion.term,
        normalized_term=suggestion.normalized_term,
        topic=suggestion.topic,
        subtopic=suggestion.subtopic,
        english_definition=suggestion.english_definition,
        vietnamese_translation=suggestion.vietnamese_translation,
        example=suggestion.example,
        exam_trap=suggestion.exam_trap,
        tags=suggestion.tags,
        item_type="research",
        difficulty=suggestion.difficulty,
        priority_score=suggestion.priority_score,
        qa_status="approved",
        confidence_score=0.75,
        status="active",
        source_reason=suggestion.research_reason or "OpenAI web research approved by user",
    )
    session.add(vocab)
    session.flush()

    for alias in suggestion.aliases:
        normalized_alias = normalize_term(alias)
        alias_exists = session.scalar(
            select(VocabAlias).where(VocabAlias.normalized_alias == normalized_alias)
        )
        if normalized_alias and normalized_alias != vocab.normalized_term and alias_exists is None:
            session.add(
                VocabAlias(
                    vocab_id=vocab.id,
                    alias=alias,
                    normalized_alias=normalized_alias,
                    alias_type="abbreviation" if alias.isupper() else "variant",
                )
            )

    sources = suggestion.sources or [
        {"source_name": "OpenAI web research", "source_type": "openai_web_research"}
    ]
    for source in sources:
        reference = source.get("source_reference") or source.get("url")
        session.add(
            VocabSource(
                vocab_id=vocab.id,
                source_name=source.get("source_name", "OpenAI web research"),
                source_type=source.get("source_type", "public_web"),
                source_reference=reference,
                confidence_score=0.75,
                copyright_status="term_extracted_content_rewritten",
            )
        )

    suggestion.status = "approved"
    suggestion.vocab_id = vocab.id
    suggestion.approved_at = utc_now()
    session.flush()
    return suggestion, vocab, "approved"


def reject_research_suggestion(
    session: Session,
    *,
    user: User,
    suggestion_id: int,
) -> ResearchSuggestion:
    suggestion = session.get(ResearchSuggestion, suggestion_id)
    if suggestion is None or suggestion.user_id != user.id:
        raise ValueError("Research suggestion not found.")
    suggestion.status = "rejected"
    session.flush()
    return suggestion


def pending_research_suggestions(
    session: Session, *, user: User, limit: int = 20
) -> list[ResearchSuggestion]:
    return list(
        session.scalars(
            select(ResearchSuggestion)
            .where(ResearchSuggestion.user_id == user.id, ResearchSuggestion.status == "suggested")
            .order_by(ResearchSuggestion.created_at.desc(), ResearchSuggestion.priority_score.desc())
            .limit(limit)
        )
    )
