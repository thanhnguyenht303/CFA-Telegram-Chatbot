from __future__ import annotations

import datetime as dt
import random
from collections.abc import Sequence

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import (
    QuizAttempt,
    QuizQuestion,
    QuizResult,
    StudyPlan,
    User,
    VocabItem,
    utc_now,
)
from cfa_vocab_bot.services.content_engine import _approved_vocab_query, current_plan, weekly_vocab
from cfa_vocab_bot.services.spaced_repetition import apply_review_result, get_or_create_review_state

QUESTION_TYPES = [
    "meaning_mc",
    "fill_blank",
    "match_definition",
    "distinguish_confusing_terms",
    "cfa_style",
]


def _choice_letter(index: int) -> str:
    return ["A", "B", "C"][index]


def _options_for_vocab(
    rng: random.Random,
    vocab: VocabItem,
    distractors: Sequence[VocabItem],
    *,
    use_terms: bool,
) -> tuple[dict[str, str], str]:
    correct = vocab.term if use_terms else vocab.english_definition
    wrong_values = []
    for item in distractors:
        wrong_values.append(item.term if use_terms else item.english_definition)
    while len(wrong_values) < 2:
        wrong_values.append("A related but less precise CFA concept.")
    values = [correct, wrong_values[0], wrong_values[1]]
    rng.shuffle(values)
    correct_index = values.index(correct)
    return {"A": values[0], "B": values[1], "C": values[2]}, _choice_letter(correct_index)


def _distractors(pool: Sequence[VocabItem], vocab: VocabItem, count: int = 2) -> list[VocabItem]:
    choices = [item for item in pool if item.id != vocab.id]
    same_topic = [item for item in choices if item.topic == vocab.topic]
    result = same_topic[:count]
    if len(result) < count:
        result.extend(choices[: count - len(result)])
    return result[:count]


def _build_question(
    *,
    quiz_id: int,
    vocab: VocabItem,
    pool: Sequence[VocabItem],
    order_index: int,
) -> QuizQuestion:
    rng = random.Random(quiz_id * 1000 + vocab.id)
    question_type = QUESTION_TYPES[order_index % len(QUESTION_TYPES)]
    distractors = _distractors(pool, vocab)

    if question_type == "meaning_mc":
        options, answer = _options_for_vocab(rng, vocab, distractors, use_terms=False)
        text = f'Which option best describes "{vocab.term}"?'
    elif question_type == "fill_blank":
        options, answer = _options_for_vocab(rng, vocab, distractors, use_terms=True)
        text = f"Fill in the blank: {vocab.example.replace(vocab.term, '_____')}"
    elif question_type == "match_definition":
        options, answer = _options_for_vocab(rng, vocab, distractors, use_terms=True)
        text = f"Match the term to this definition: {vocab.english_definition}"
    elif question_type == "distinguish_confusing_terms":
        options, answer = _options_for_vocab(rng, vocab, distractors, use_terms=True)
        other = distractors[0].term if distractors else "a similar concept"
        text = f"Which term is most likely confused with {other}, but fits this trap: {vocab.exam_trap}"
    else:
        options, answer = _options_for_vocab(rng, vocab, distractors, use_terms=True)
        text = (
            "A CFA Level I question stem says: "
            f'"{vocab.example}" Which term is most appropriate?'
        )

    return QuizQuestion(
        quiz_id=quiz_id,
        vocab_id=vocab.id,
        question_type=question_type,
        question_text=text,
        option_a=options["A"],
        option_b=options["B"],
        option_c=options["C"],
        correct_answer=answer,
        explanation=(
            f"{vocab.term}: {vocab.english_definition} "
            f"Exam trap: {vocab.exam_trap or 'Focus on the CFA context.'}"
        ),
        difficulty=vocab.difficulty,
        order_index=order_index,
    )


def _fallback_vocab_for_plan(
    session: Session, plan: StudyPlan | None, exclude_ids: set[int], needed: int
) -> list[VocabItem]:
    query = _approved_vocab_query().where(~VocabItem.id.in_(exclude_ids))
    if plan:
        topic_rows = list(
            session.scalars(
                query.where(VocabItem.topic == plan.main_topic)
                .order_by(VocabItem.priority_score.desc(), VocabItem.id.asc())
                .limit(needed)
            )
        )
        if len(topic_rows) >= needed:
            return topic_rows
        exclude_ids.update(item.id for item in topic_rows)
        return topic_rows + list(
            session.scalars(
                _approved_vocab_query()
                .where(~VocabItem.id.in_(exclude_ids))
                .order_by(VocabItem.priority_score.desc(), VocabItem.id.asc())
                .limit(needed - len(topic_rows))
            )
        )
    return list(
        session.scalars(query.order_by(VocabItem.priority_score.desc(), VocabItem.id.asc()).limit(needed))
    )


def create_weekly_quiz(
    session: Session,
    user: User,
    *,
    today: dt.date | None = None,
    question_count: int = 20,
) -> QuizResult:
    plan = current_plan(session, user, today or dt.date.today())
    vocab = weekly_vocab(session, user, plan) if plan else []
    unique: list[VocabItem] = []
    seen_ids: set[int] = set()
    for item in vocab:
        if item.id not in seen_ids:
            unique.append(item)
            seen_ids.add(item.id)
    if len(unique) < question_count:
        unique.extend(_fallback_vocab_for_plan(session, plan, seen_ids, question_count - len(unique)))
    if not unique:
        raise ValueError("No approved vocabulary is available for quiz generation.")
    selected = unique[:question_count]

    quiz = QuizResult(
        user_id=user.id,
        study_plan_id=plan.id if plan else None,
        week_number=plan.week_number if plan else None,
        topic=plan.main_topic if plan else None,
        total_questions=len(selected),
        status="active",
    )
    session.add(quiz)
    session.flush()

    pool = unique if len(unique) >= 3 else list(session.scalars(_approved_vocab_query().limit(10)))
    for index, vocab_item in enumerate(selected):
        session.add(_build_question(quiz_id=quiz.id, vocab=vocab_item, pool=pool, order_index=index))
    session.flush()
    return quiz


def active_quiz(session: Session, user: User) -> QuizResult | None:
    return session.scalar(
        select(QuizResult)
        .where(QuizResult.user_id == user.id, QuizResult.status == "active")
        .order_by(QuizResult.started_at.desc())
    )


def next_unanswered_question(session: Session, user: User, quiz: QuizResult) -> QuizQuestion | None:
    answered = select(QuizAttempt.question_id).where(
        QuizAttempt.user_id == user.id,
        QuizAttempt.quiz_id == quiz.id,
    )
    return session.scalar(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz.id, ~QuizQuestion.id.in_(answered))
        .order_by(QuizQuestion.order_index.asc())
    )


def grade_answer(
    session: Session,
    *,
    user: User,
    quiz: QuizResult,
    question: QuizQuestion,
    selected_answer: str,
    response_time_seconds: int | None = None,
) -> QuizAttempt:
    selected = selected_answer.strip().upper()
    existing = session.scalar(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user.id,
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.question_id == question.id,
        )
    )
    if existing:
        return existing
    is_correct = selected == question.correct_answer.upper()
    attempt = QuizAttempt(
        user_id=user.id,
        quiz_id=quiz.id,
        question_id=question.id,
        selected_answer=selected,
        is_correct=is_correct,
        response_time_seconds=response_time_seconds,
    )
    session.add(attempt)
    state = get_or_create_review_state(session, user.id, question.vocab_id)
    apply_review_result(state, is_correct, reason="quiz")
    session.flush()
    refresh_quiz_score(session, quiz)
    return attempt


def refresh_quiz_score(session: Session, quiz: QuizResult) -> QuizResult:
    total, correct = session.execute(
        select(func.count(QuizAttempt.id), func.sum(func.cast(QuizAttempt.is_correct, Integer))).where(
            QuizAttempt.quiz_id == quiz.id
        )
    ).one()
    total = int(total or 0)
    correct = int(correct or 0)
    quiz.correct_answers = correct
    if quiz.total_questions:
        quiz.score_percent = round(correct / quiz.total_questions * 100, 2)
    if total >= quiz.total_questions and quiz.total_questions > 0:
        quiz.status = "completed"
        quiz.submitted_at = utc_now()
    return quiz


def quiz_feedback(session: Session, quiz: QuizResult) -> str:
    wrong_rows = session.execute(
        select(QuizQuestion, VocabItem)
        .join(VocabItem, VocabItem.id == QuizQuestion.vocab_id)
        .join(QuizAttempt, QuizAttempt.question_id == QuizQuestion.id)
        .where(QuizQuestion.quiz_id == quiz.id, QuizAttempt.is_correct.is_(False))
        .order_by(QuizQuestion.order_index.asc())
    ).all()
    wrong_terms = ", ".join(vocab.term for _, vocab in wrong_rows) or "none"
    action = (
        "These will appear again in review."
        if quiz.score_percent < 85
        else "Nice work. Mastered terms will still return after a longer interval."
    )
    return (
        f"Your score: {quiz.correct_answers}/{quiz.total_questions} = {quiz.score_percent:.0f}%.\n"
        f"Weak terms: {wrong_terms}.\n"
        f"{action}"
    )
