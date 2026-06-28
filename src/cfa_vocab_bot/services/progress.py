from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import DeliveryLog, QuizResult, ReviewState, User, VocabItem, utc_now
from cfa_vocab_bot.schemas import ProgressSnapshot
from cfa_vocab_bot.services.content_engine import current_plan, next_plan, review_debt


def _as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def _streak_days(session: Session, user: User, today: dt.date | None = None) -> int:
    timezone = ZoneInfo(user.settings.timezone)
    today = today or utc_now().astimezone(timezone).date()
    rows = session.scalars(
        select(DeliveryLog.sent_at)
        .where(DeliveryLog.user_id == user.id, DeliveryLog.delivery_type == "daily_vocab")
        .order_by(DeliveryLog.sent_at.desc())
    ).all()
    sent_dates = {_as_utc(value).astimezone(timezone).date() for value in rows}
    streak = 0
    cursor = today
    while cursor in sent_dates:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak


def latest_quiz_score(session: Session, user: User) -> float | None:
    quiz = session.scalar(
        select(QuizResult)
        .where(QuizResult.user_id == user.id, QuizResult.status == "completed")
        .order_by(QuizResult.submitted_at.desc().nullslast(), QuizResult.id.desc())
    )
    return quiz.score_percent if quiz else None


def weighted_readiness(session: Session, user: User) -> dict[str, float]:
    rows = session.execute(
        select(
            VocabItem.topic,
            func.avg(ReviewState.mastery_level),
            func.max(VocabItem.official_topic_weight),
        )
        .join(ReviewState, ReviewState.vocab_id == VocabItem.id)
        .where(ReviewState.user_id == user.id)
        .group_by(VocabItem.topic)
    ).all()
    readiness: dict[str, float] = {}
    for topic, avg_mastery, topic_weight in rows:
        base = float(avg_mastery or 0) / 5 * 100
        weight = float(topic_weight or 1.0)
        readiness[str(topic)] = round(base * min(weight, 100) / max(weight, 1.0), 1)
    return readiness


def progress_snapshot(session: Session, user: User, today: dt.date | None = None) -> ProgressSnapshot:
    today = today or utc_now().astimezone(ZoneInfo(user.settings.timezone)).date()
    totals = session.execute(
        select(
            func.count(ReviewState.id),
            func.sum(func.cast(ReviewState.status == "mastered", Integer)),
            func.sum(func.cast(ReviewState.status == "reviewing", Integer)),
            func.sum(func.cast(ReviewState.is_weak, Integer)),
        ).where(ReviewState.user_id == user.id)
    ).one()
    plan = current_plan(session, user, today)
    upcoming = next_plan(session, user, today)
    return ProgressSnapshot(
        total_terms_seen=int(totals[0] or 0),
        mastered=int(totals[1] or 0),
        reviewing=int(totals[2] or 0),
        weak=int(totals[3] or 0),
        weekly_quiz_score=latest_quiz_score(session, user),
        current_topic=plan.main_topic if plan else None,
        next_topic=upcoming.main_topic if upcoming else None,
        streak_days=_streak_days(session, user, today),
        review_debt=review_debt(session, user, utc_now()),
        weighted_readiness=weighted_readiness(session, user),
    )


def format_progress(snapshot: ProgressSnapshot) -> str:
    weighted = "\n".join(
        f"- {topic}: {score:.1f}%" for topic, score in snapshot.weighted_readiness.items()
    )
    weighted_block = f"\n\nWeighted readiness:\n{weighted}" if weighted else ""
    quiz_score = (
        f"{snapshot.weekly_quiz_score:.0f}%" if snapshot.weekly_quiz_score is not None else "n/a"
    )
    return (
        "CFA Vocab Progress\n"
        f"Total terms learned: {snapshot.total_terms_seen}\n"
        f"Mastered: {snapshot.mastered}\n"
        f"Reviewing: {snapshot.reviewing}\n"
        f"Weak: {snapshot.weak}\n"
        f"Weekly quiz score: {quiz_score}\n"
        f"Current topic: {snapshot.current_topic or 'not set'}\n"
        f"Next topic: {snapshot.next_topic or 'not set'}\n"
        f"Current streak: {snapshot.streak_days} days\n"
        f"Review debt: {snapshot.review_debt} terms"
        f"{weighted_block}"
    )
