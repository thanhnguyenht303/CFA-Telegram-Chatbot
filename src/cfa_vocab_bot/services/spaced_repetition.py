from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import ReviewState, utc_now

CORRECT_INTERVALS = {
    1: 3,
    2: 7,
    3: 14,
    4: 30,
}


def get_or_create_review_state(session: Session, user_id: int, vocab_id: int) -> ReviewState:
    state = session.scalar(
        select(ReviewState).where(
            ReviewState.user_id == user_id,
            ReviewState.vocab_id == vocab_id,
        )
    )
    if state:
        return state
    state = ReviewState(
        user_id=user_id,
        vocab_id=vocab_id,
        status="new",
        mastery_level=0,
        next_review_at=utc_now() + dt.timedelta(days=1),
        due_reason="new",
    )
    session.add(state)
    session.flush()
    return state


def next_interval_for_correct(correct_count: int) -> int:
    return CORRECT_INTERVALS.get(min(correct_count, 4), 30)


def apply_review_result(
    state: ReviewState,
    is_correct: bool,
    reviewed_at: dt.datetime | None = None,
    reason: str | None = None,
) -> ReviewState:
    reviewed_at = reviewed_at or utc_now()
    state.last_reviewed_at = reviewed_at
    state.correct_count = state.correct_count or 0
    state.wrong_count = state.wrong_count or 0
    state.mastery_level = state.mastery_level or 0
    state.ease_factor = state.ease_factor or 2.3

    if is_correct:
        state.correct_count += 1
        state.mastery_level = min(5, state.mastery_level + 1)
        state.interval_days = next_interval_for_correct(state.correct_count)
        state.next_review_at = reviewed_at + dt.timedelta(days=state.interval_days)
        state.is_weak = state.wrong_count >= 2 and state.correct_count < state.wrong_count + 2
        state.status = "mastered" if state.correct_count >= 4 and not state.is_weak else "reviewing"
        state.due_reason = reason or "correct"
        state.ease_factor = min(3.0, state.ease_factor + 0.1)
    else:
        state.wrong_count += 1
        state.mastery_level = max(0, state.mastery_level - 1)
        state.interval_days = 1
        state.next_review_at = reviewed_at + dt.timedelta(days=1)
        state.is_weak = state.wrong_count >= 2
        state.status = "weak" if state.is_weak else "reviewing"
        state.due_reason = reason or "wrong"
        state.ease_factor = max(1.3, state.ease_factor - 0.2)

    return state


def mark_seen(session: Session, user_id: int, vocab_id: int) -> ReviewState:
    state = get_or_create_review_state(session, user_id, vocab_id)
    if state.status == "new":
        state.next_review_at = utc_now() + dt.timedelta(days=1)
        state.due_reason = "daily_vocab"
    return state
