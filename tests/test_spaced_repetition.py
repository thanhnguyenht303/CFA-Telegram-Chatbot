from __future__ import annotations

import datetime as dt

from cfa_vocab_bot.models import ReviewState
from cfa_vocab_bot.services.spaced_repetition import apply_review_result


def test_spaced_repetition_correct_intervals():
    now = dt.datetime(2026, 6, 24, 12, tzinfo=dt.UTC)
    state = ReviewState(user_id=1, vocab_id=1)
    apply_review_result(state, True, reviewed_at=now)
    assert state.interval_days == 3
    assert state.next_review_at == now + dt.timedelta(days=3)
    apply_review_result(state, True, reviewed_at=now)
    assert state.interval_days == 7
    apply_review_result(state, True, reviewed_at=now)
    assert state.interval_days == 14
    apply_review_result(state, True, reviewed_at=now)
    assert state.interval_days == 30
    assert state.status == "mastered"


def test_wrong_answers_return_next_day_and_become_weak():
    now = dt.datetime(2026, 6, 24, 12, tzinfo=dt.UTC)
    state = ReviewState(user_id=1, vocab_id=1)
    apply_review_result(state, False, reviewed_at=now)
    assert state.next_review_at == now + dt.timedelta(days=1)
    assert state.status == "reviewing"
    apply_review_result(state, False, reviewed_at=now)
    assert state.is_weak is True
    assert state.status == "weak"

