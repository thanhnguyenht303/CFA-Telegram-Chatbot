from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import (
    DeliveryLog,
    QuizAttempt,
    QuizQuestion,
    QuizResult,
    ResearchSuggestion,
    ReviewState,
    SchedulerJob,
    StudyPlan,
    SystemEvent,
    User,
)


def delete_user_data(session: Session, user: User) -> None:
    quiz_ids = [row.id for row in session.query(QuizResult.id).filter(QuizResult.user_id == user.id)]
    if quiz_ids:
        session.execute(delete(QuizAttempt).where(QuizAttempt.quiz_id.in_(quiz_ids)))
        session.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id.in_(quiz_ids)))
    session.execute(delete(QuizResult).where(QuizResult.user_id == user.id))
    session.execute(delete(DeliveryLog).where(DeliveryLog.user_id == user.id))
    session.execute(delete(ReviewState).where(ReviewState.user_id == user.id))
    session.execute(delete(ResearchSuggestion).where(ResearchSuggestion.user_id == user.id))
    session.execute(delete(SchedulerJob).where(SchedulerJob.user_id == user.id))
    session.execute(delete(SystemEvent).where(SystemEvent.user_id == user.id))
    session.execute(delete(StudyPlan).where(StudyPlan.user_id == user.id))
    session.delete(user)
