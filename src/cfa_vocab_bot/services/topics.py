from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import VocabItem

APPROVED_TOPIC_STATUSES = {"approved", "auto_approved"}


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

