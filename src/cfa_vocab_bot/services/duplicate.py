from __future__ import annotations

import re
import unicodedata

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import VocabAlias, VocabItem

_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_SPACE_RE = re.compile(r"\s+")

COMMON_ALIASES = {
    "ytm": "yield to maturity",
    "ear": "effective annual rate",
    "hpr": "holding period return",
    "cogs": "cost of goods sold",
    "dtl": "deferred tax liability",
    "fcfe": "free cash flow to equity",
    "wacc": "weighted average cost of capital",
    "ocf": "operating cash flow",
}


def normalize_term(term: str, alias_map: dict[str, str] | None = None) -> str:
    """Normalize terms so spelling variants and abbreviations can be deduplicated."""

    ascii_term = unicodedata.normalize("NFKD", term).encode("ascii", "ignore").decode("ascii")
    lowered = ascii_term.lower().replace("&", " and ")
    lowered = lowered.replace("-", " ").replace("/", " ")
    no_punctuation = _NON_WORD_RE.sub(" ", lowered)
    compact = _SPACE_RE.sub(" ", no_punctuation).strip()
    aliases = {**COMMON_ALIASES, **(alias_map or {})}
    return aliases.get(compact, compact)


def load_alias_map(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(VocabAlias.normalized_alias, VocabItem.normalized_term).join(VocabItem)
    ).all()
    return {alias: canonical for alias, canonical in rows}


def duplicate_query(term: str, topic: str | None, subtopic: str | None = None) -> Select[tuple[VocabItem]]:
    normalized = normalize_term(term)
    conditions = [VocabItem.normalized_term == normalized]
    alias_subquery = select(VocabAlias.vocab_id).where(VocabAlias.normalized_alias == normalized)
    conditions.append(VocabItem.id.in_(alias_subquery))
    query = select(VocabItem).where(or_(*conditions))
    if topic:
        query = query.where(VocabItem.topic == topic)
    if subtopic is not None:
        query = query.where(VocabItem.subtopic == subtopic)
    return query


def find_duplicate(
    session: Session, term: str, topic: str | None, subtopic: str | None = None
) -> VocabItem | None:
    alias_map = load_alias_map(session)
    normalized = normalize_term(term, alias_map)
    query = select(VocabItem).where(VocabItem.normalized_term == normalized)
    if topic:
        query = query.where(VocabItem.topic == topic)
    if subtopic is not None:
        query = query.where(VocabItem.subtopic == subtopic)
    found = session.scalar(query)
    if found:
        return found
    alias = session.scalar(select(VocabAlias).where(VocabAlias.normalized_alias == normalized))
    if alias:
        return alias.vocab
    return None


def is_duplicate(session: Session, term: str, topic: str | None, subtopic: str | None = None) -> bool:
    return find_duplicate(session, term, topic, subtopic) is not None

