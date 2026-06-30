from __future__ import annotations

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import (
    DeliveryLog,
    QuizAttempt,
    QuizResult,
    ResearchSuggestion,
    ReviewState,
    TopicLearningSetting,
    User,
    VocabItem,
)


def export_vocab_csv(session: Session, user: User) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "term",
            "topic",
            "subtopic",
            "english_definition",
            "vietnamese_translation",
            "example",
            "exam_trap",
            "mastery_level",
            "correct_count",
            "wrong_count",
            "status",
        ]
    )
    rows = session.execute(
        select(VocabItem, ReviewState)
        .join(ReviewState, ReviewState.vocab_id == VocabItem.id)
        .where(ReviewState.user_id == user.id)
        .order_by(VocabItem.topic, VocabItem.term)
    ).all()
    for vocab, state in rows:
        writer.writerow(
            [
                vocab.term,
                vocab.topic,
                vocab.subtopic or "",
                vocab.english_definition,
                vocab.vietnamese_translation,
                vocab.example,
                vocab.exam_trap or "",
                state.mastery_level,
                state.correct_count,
                state.wrong_count,
                state.status,
            ]
        )
    return output.getvalue()


def export_anki_tsv(session: Session, user: User) -> str:
    lines = []
    rows = session.scalars(
        select(VocabItem)
        .join(ReviewState, ReviewState.vocab_id == VocabItem.id)
        .where(ReviewState.user_id == user.id)
        .order_by(VocabItem.topic, VocabItem.term)
    )
    for vocab in rows:
        front = f"{vocab.term} ({vocab.topic})"
        back = (
            f"{vocab.english_definition}<br>"
            f"Vietnamese: {vocab.vietnamese_translation}<br>"
            f"Example: {vocab.example}<br>"
            f"Exam trap: {vocab.exam_trap or 'n/a'}"
        )
        lines.append(f"{front}\t{back}")
    return "\n".join(lines) + ("\n" if lines else "")


def export_all_user_data(session: Session, user: User) -> str:
    review_rows = session.execute(
        select(VocabItem, ReviewState)
        .join(ReviewState, ReviewState.vocab_id == VocabItem.id)
        .where(ReviewState.user_id == user.id)
    ).all()
    quiz_rows = session.scalars(select(QuizResult).where(QuizResult.user_id == user.id)).all()
    attempts = session.scalars(select(QuizAttempt).where(QuizAttempt.user_id == user.id)).all()
    deliveries = session.scalars(select(DeliveryLog).where(DeliveryLog.user_id == user.id)).all()
    research_suggestions = session.scalars(
        select(ResearchSuggestion).where(ResearchSuggestion.user_id == user.id)
    ).all()
    learning_settings = session.scalars(
        select(TopicLearningSetting).where(TopicLearningSetting.user_id == user.id)
    ).all()
    payload = {
        "user": {
            "telegram_user_id": user.telegram_user_id,
            "chat_id": user.chat_id,
            "username": user.username,
            "first_name": user.first_name,
        },
        "settings": {
            "timezone": user.settings.timezone,
            "daily_vocab_count": user.settings.daily_vocab_count,
            "review_intensity": user.settings.review_intensity,
            "exam_date": user.settings.exam_date.isoformat() if user.settings.exam_date else None,
        },
        "review_state": [
            {
                "term": vocab.term,
                "topic": vocab.topic,
                "mastery_level": state.mastery_level,
                "status": state.status,
                "correct_count": state.correct_count,
                "wrong_count": state.wrong_count,
                "next_review_at": state.next_review_at.isoformat()
                if state.next_review_at
                else None,
            }
            for vocab, state in review_rows
        ],
        "quiz_results": [
            {
                "quiz_id": quiz.id,
                "topic": quiz.topic,
                "score_percent": quiz.score_percent,
                "submitted_at": quiz.submitted_at.isoformat() if quiz.submitted_at else None,
            }
            for quiz in quiz_rows
        ],
        "quiz_attempts": [
            {
                "quiz_id": attempt.quiz_id,
                "question_id": attempt.question_id,
                "selected_answer": attempt.selected_answer,
                "is_correct": attempt.is_correct,
                "answered_at": attempt.answered_at.isoformat(),
            }
            for attempt in attempts
        ],
        "delivery_log": [
            {
                "delivery_type": log.delivery_type,
                "topic": log.topic,
                "normalized_term": log.normalized_term,
                "sent_at": log.sent_at.isoformat(),
                "status": log.status,
            }
            for log in deliveries
        ],
        "research_suggestions": [
            {
                "id": suggestion.id,
                "term": suggestion.term,
                "topic": suggestion.topic,
                "status": suggestion.status,
                "sources": suggestion.sources,
                "created_at": suggestion.created_at.isoformat(),
                "approved_at": suggestion.approved_at.isoformat()
                if suggestion.approved_at
                else None,
            }
            for suggestion in research_suggestions
        ],
        "topic_learning_settings": [
            {
                "topic": setting.topic,
                "weeks": setting.weeks,
                "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
            }
            for setting in learning_settings
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
