from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import VocabItem

APPROVED_TOPIC_STATUSES = {"approved", "auto_approved"}
TOPIC_SUGGESTION_CUTOFF = 0.68


@dataclass(frozen=True)
class TopicResolution:
    topic: str | None
    suggestion: str | None
    available_topics: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return self.topic is not None


def normalize_topic_key(topic: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", topic.casefold())).strip()


def available_topic_counts(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(VocabItem.topic, func.count(VocabItem.id))
        .where(
            VocabItem.status == "active",
            VocabItem.qa_status.in_(APPROVED_TOPIC_STATUSES),
        )
        .group_by(VocabItem.topic)
        .order_by(VocabItem.topic.asc())
    ).all()
    return [(str(topic), int(count)) for topic, count in rows if topic]


def available_topic_names(session: Session) -> list[str]:
    return [topic for topic, _ in available_topic_counts(session)]


def resolve_topic_for_learning(session: Session, topic: str) -> TopicResolution:
    """Validate a user-entered topic against the approved vocab pool."""
    clean_topic = re.sub(r"\s+", " ", topic.strip())
    available_topics = tuple(available_topic_names(session))
    if not available_topics:
        return TopicResolution(topic=clean_topic, suggestion=None, available_topics=available_topics)

    normalized_map = {normalize_topic_key(name): name for name in available_topics}
    normalized = normalize_topic_key(clean_topic)
    if normalized in normalized_map:
        return TopicResolution(
            topic=normalized_map[normalized],
            suggestion=None,
            available_topics=available_topics,
        )

    suggestion = _suggest_topic(normalized, normalized_map)
    return TopicResolution(topic=None, suggestion=suggestion, available_topics=available_topics)


def _suggest_topic(normalized: str, normalized_map: dict[str, str]) -> str | None:
    if not normalized:
        return None
    substring_matches = [
        display
        for key, display in normalized_map.items()
        if len(normalized) >= 4 and (normalized in key or key in normalized)
    ]
    if len(substring_matches) == 1:
        return substring_matches[0]

    acronym_matches = [
        display
        for key, display in normalized_map.items()
        if len(normalized) >= 2 and _topic_acronym(key).endswith(normalized)
    ]
    if len(acronym_matches) == 1:
        return acronym_matches[0]

    matches = get_close_matches(
        normalized,
        list(normalized_map),
        n=1,
        cutoff=TOPIC_SUGGESTION_CUTOFF,
    )
    if matches:
        return normalized_map[matches[0]]

    scored = [
        (SequenceMatcher(None, normalized, key).ratio(), display)
        for key, display in normalized_map.items()
    ]
    score, display = max(scored, default=(0.0, None))
    return display if score >= TOPIC_SUGGESTION_CUTOFF else None


def _topic_acronym(normalized_topic: str) -> str:
    return "".join(word[0] for word in normalized_topic.split() if word)
