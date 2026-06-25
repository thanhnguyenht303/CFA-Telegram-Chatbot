from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import DeliveryLog, ReviewState, StudyPlan, User, VocabItem, utc_now
from cfa_vocab_bot.services.importers import next_plan_after, plan_for_date
from cfa_vocab_bot.services.spaced_repetition import mark_seen

APPROVED_QA_STATUSES = {"approved", "auto_approved"}


def _date_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(day, dt.time.max, tzinfo=dt.UTC)
    return start, end


def current_plan(session: Session, user: User, today: dt.date | None = None) -> StudyPlan | None:
    return plan_for_date(session, user.id, today or dt.date.today())


def next_plan(session: Session, user: User, today: dt.date | None = None) -> StudyPlan | None:
    return next_plan_after(session, user.id, today or dt.date.today())


def _approved_vocab_query():
    return select(VocabItem).where(
        VocabItem.status == "active",
        VocabItem.qa_status.in_(APPROVED_QA_STATUSES),
    )


def _already_sent_daily_subquery(user_id: int):
    return select(DeliveryLog.vocab_id).where(
        DeliveryLog.user_id == user_id,
        DeliveryLog.delivery_type == "daily_vocab",
        DeliveryLog.vocab_id.is_not(None),
    )


def _topic_match(topic: str):
    return or_(VocabItem.topic == topic, VocabItem.tags.contains([topic]))


def select_daily_vocab(
    session: Session,
    user: User,
    *,
    today: dt.date | None = None,
    count: int | None = None,
) -> tuple[StudyPlan | None, list[VocabItem]]:
    today = today or dt.date.today()
    plan = current_plan(session, user, today)
    count = count or user.settings.daily_vocab_count
    sent = _already_sent_daily_subquery(user.id)

    query = _approved_vocab_query().where(not_(VocabItem.id.in_(sent)))
    if plan:
        topic_query = query.where(_topic_match(plan.main_topic)).order_by(
            VocabItem.priority_score.desc(), VocabItem.id.asc()
        )
        vocab = list(session.scalars(topic_query.limit(count)).all())
        if len(vocab) >= count:
            return plan, vocab
        seen_ids = {item.id for item in vocab}
        fallback = list(
            session.scalars(
                query.where(not_(VocabItem.id.in_(seen_ids))).order_by(
                    VocabItem.priority_score.desc(), VocabItem.id.asc()
                )
            )
            .unique()
            .fetchmany(count - len(vocab))
        )
        return plan, vocab + fallback

    vocab = list(
        session.scalars(query.order_by(VocabItem.priority_score.desc(), VocabItem.id.asc()).limit(count))
    )
    return None, vocab


def record_vocab_delivery(
    session: Session,
    *,
    user: User,
    vocab_items: Sequence[VocabItem],
    delivery_type: str,
    plan: StudyPlan | None = None,
    message_id: int | None = None,
    sent_at: dt.datetime | None = None,
) -> None:
    sent_at = sent_at or utc_now()
    day_index = sent_at.weekday()
    for vocab in vocab_items:
        session.add(
            DeliveryLog(
                user_id=user.id,
                vocab_id=vocab.id,
                study_plan_id=plan.id if plan else None,
                delivery_type=delivery_type,
                status="sent",
                sent_at=sent_at,
                week_number=plan.week_number if plan else None,
                day_index=day_index,
                message_id=message_id,
                normalized_term=vocab.normalized_term,
                topic=vocab.topic,
                payload={"term": vocab.term},
            )
        )
        mark_seen(session, user.id, vocab.id)


def todays_vocab(session: Session, user: User, today: dt.date | None = None) -> list[VocabItem]:
    today = today or dt.date.today()
    start, end = _date_bounds(today)
    return list(
        session.scalars(
            select(VocabItem)
            .join(DeliveryLog, DeliveryLog.vocab_id == VocabItem.id)
            .where(
                DeliveryLog.user_id == user.id,
                DeliveryLog.delivery_type == "daily_vocab",
                DeliveryLog.sent_at >= start,
                DeliveryLog.sent_at <= end,
            )
            .order_by(DeliveryLog.id.asc())
        )
    )


def select_review_vocab(
    session: Session,
    user: User,
    *,
    now: dt.datetime | None = None,
    count: int = 5,
) -> list[VocabItem]:
    now = now or utc_now()
    due = list(
        session.scalars(
            select(VocabItem)
            .join(ReviewState, ReviewState.vocab_id == VocabItem.id)
            .where(
                ReviewState.user_id == user.id,
                ReviewState.next_review_at.is_not(None),
                ReviewState.next_review_at <= now,
            )
            .order_by(ReviewState.is_weak.desc(), ReviewState.next_review_at.asc())
            .limit(count)
        )
    )
    if len(due) >= count:
        return due

    seen_ids = {item.id for item in due}
    today_items = [item for item in todays_vocab(session, user, now.date()) if item.id not in seen_ids]
    return due + today_items[: count - len(due)]


def weak_vocab(session: Session, user: User, *, limit: int = 10) -> list[tuple[VocabItem, ReviewState]]:
    rows = session.execute(
        select(VocabItem, ReviewState)
        .join(ReviewState, ReviewState.vocab_id == VocabItem.id)
        .where(
            ReviewState.user_id == user.id,
            or_(ReviewState.is_weak.is_(True), ReviewState.wrong_count > 0),
        )
        .order_by(ReviewState.wrong_count.desc(), ReviewState.next_review_at.asc())
        .limit(limit)
    ).all()
    return [(vocab, state) for vocab, state in rows]


def weekly_vocab(session: Session, user: User, plan: StudyPlan) -> list[VocabItem]:
    start = dt.datetime.combine(plan.start_date, dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(plan.end_date, dt.time.max, tzinfo=dt.UTC)
    return list(
        session.scalars(
            select(VocabItem)
            .join(DeliveryLog, DeliveryLog.vocab_id == VocabItem.id)
            .where(
                DeliveryLog.user_id == user.id,
                DeliveryLog.delivery_type == "daily_vocab",
                DeliveryLog.sent_at >= start,
                DeliveryLog.sent_at <= end,
            )
            .order_by(DeliveryLog.sent_at.asc(), DeliveryLog.id.asc())
        )
    )


def explain_selection(session: Session, user: User, vocab: VocabItem, plan: StudyPlan | None) -> str:
    weakness = session.scalar(
        select(ReviewState).where(ReviewState.user_id == user.id, ReviewState.vocab_id == vocab.id)
    )
    parts = [
        f"topic={vocab.topic}",
        f"priority={vocab.priority_score:.1f}",
        f"qa={vocab.qa_status}",
    ]
    if plan:
        parts.append(f"week={plan.week_number}")
    if weakness and weakness.is_weak:
        parts.append("personal_weakness=true")
    return "; ".join(parts)


def review_debt(session: Session, user: User, now: dt.datetime | None = None) -> int:
    now = now or utc_now()
    return int(
        session.scalar(
            select(func.count(ReviewState.id)).where(
                ReviewState.user_id == user.id,
                ReviewState.next_review_at.is_not(None),
                ReviewState.next_review_at <= now,
            )
        )
        or 0
    )


def terms_due_for_mini_review(session: Session, user: User) -> list[VocabItem]:
    return select_review_vocab(session, user, count=3)
