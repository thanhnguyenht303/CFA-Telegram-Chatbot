from __future__ import annotations

import datetime as dt

from cfa_vocab_bot.models import ReviewState
from cfa_vocab_bot.services.content_engine import record_vocab_delivery, select_daily_vocab
from cfa_vocab_bot.services.importers import import_timeline
from cfa_vocab_bot.services.quiz import create_weekly_quiz, grade_answer, next_unanswered_question


def test_weekly_quiz_generation_and_grading_updates_weak_terms(
    session, user, seeded, current_week_csv
):
    import_timeline(session, user_id=user.id, path=current_week_csv)
    for offset in range(5):
        plan, vocab = select_daily_vocab(
            session, user, today=dt.date(2026, 6, 22 + offset), count=5
        )
        record_vocab_delivery(session, user=user, vocab_items=vocab, delivery_type="daily_vocab", plan=plan)
        session.commit()

    quiz = create_weekly_quiz(session, user, today=dt.date(2026, 6, 27), question_count=20)
    assert quiz.total_questions == 20
    question = next_unanswered_question(session, user, quiz)
    assert question is not None
    wrong = {"A", "B", "C"}.difference({question.correct_answer}).pop()
    attempt = grade_answer(session, user=user, quiz=quiz, question=question, selected_answer=wrong)
    session.commit()
    assert attempt.is_correct is False
    assert question.vocab_id is not None
    state = session.query(ReviewState).filter_by(user_id=user.id, vocab_id=question.vocab_id).one()
    assert state.next_review_at is not None
    assert state.wrong_count == 1
