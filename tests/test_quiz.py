from __future__ import annotations

import datetime as dt

from cfa_vocab_bot.models import ReviewState, VocabItem
from cfa_vocab_bot.services.content_engine import record_vocab_delivery, select_daily_vocab
from cfa_vocab_bot.services.importers import import_timeline
from cfa_vocab_bot.services.quiz import (
    _build_question,
    create_weekly_quiz,
    grade_answer,
    next_unanswered_question,
)


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


def test_fill_blank_question_redacts_term_case_insensitively(session, seeded):
    vocab = session.query(VocabItem).filter_by(term="Operating cash flow").one()
    pool = session.query(VocabItem).limit(5).all()

    question = _build_question(quiz_id=1, vocab=vocab, pool=pool, order_index=1)

    assert question.question_type == "fill_blank"
    assert "_____" in question.question_text
    assert "Operating cash flow" not in question.question_text
    assert "operating cash flow" not in question.question_text.lower()


def test_fill_blank_question_fallback_does_not_leak_answer(session, seeded):
    vocab = session.query(VocabItem).filter_by(term="Revenue recognition").one()
    vocab.example = "A firm may record sales after satisfying a performance obligation."
    pool = session.query(VocabItem).limit(5).all()

    question = _build_question(quiz_id=1, vocab=vocab, pool=pool, order_index=1)

    assert "_____" in question.question_text
    assert "Revenue recognition" not in question.question_text
    assert "revenue recognition" not in question.question_text.lower()
