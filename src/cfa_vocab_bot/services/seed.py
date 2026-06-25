from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import VocabAlias, VocabItem, VocabSource
from cfa_vocab_bot.services.duplicate import normalize_term


def seed_vocab_from_json(session: Session, path: str | Path) -> int:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for item in payload:
        normalized = normalize_term(item["term"])
        existing = session.scalar(
            select(VocabItem).where(
                VocabItem.normalized_term == normalized,
                VocabItem.topic == item["topic"],
                VocabItem.subtopic == item.get("subtopic"),
            )
        )
        if existing:
            continue
        vocab = VocabItem(
            term=item["term"],
            normalized_term=normalized,
            topic=item["topic"],
            subtopic=item.get("subtopic"),
            pronunciation=item.get("pronunciation"),
            english_definition=item["english_definition"],
            vietnamese_translation=item["vietnamese_translation"],
            example=item["example"],
            exam_trap=item.get("exam_trap"),
            tags=item.get("tags", []),
            item_type=item.get("item_type", "vocab"),
            difficulty=item.get("difficulty", "medium"),
            priority_score=float(item.get("priority_score", 0)),
            qa_status=item.get("qa_status", "auto_approved"),
            confidence_score=float(item.get("confidence_score", 0.85)),
            curriculum_year=item.get("curriculum_year"),
            los_ids=item.get("los_ids", []),
            official_topic_weight=item.get("official_topic_weight"),
            status=item.get("status", "active"),
            source_reason=item.get("source_reason", "MVP seed vocabulary"),
        )
        session.add(vocab)
        session.flush()
        for alias in item.get("aliases", []):
            session.add(
                VocabAlias(
                    vocab_id=vocab.id,
                    alias=alias,
                    normalized_alias=normalize_term(alias),
                    alias_type="abbreviation" if alias.isupper() else "variant",
                )
            )
        for source in item.get("sources", [{"source_name": "MVP seed", "source_type": "seed"}]):
            session.add(
                VocabSource(
                    vocab_id=vocab.id,
                    source_name=source.get("source_name", "MVP seed"),
                    source_type=source.get("source_type", "seed"),
                    source_reference=source.get("source_reference"),
                    curriculum_year=source.get("curriculum_year", item.get("curriculum_year")),
                    confidence_score=float(source.get("confidence_score", item.get("confidence_score", 0.85))),
                    copyright_status=source.get("copyright_status", "rewritten_original"),
                )
            )
        count += 1
    session.flush()
    return count

