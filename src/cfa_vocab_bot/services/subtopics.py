from __future__ import annotations

import datetime as dt
import re

from sqlalchemy.orm import Session

from cfa_vocab_bot.models import StudyPlan, User
from cfa_vocab_bot.services.importers import plan_for_date

MAX_SUBTOPICS_PER_PLAN = 10


def normalize_subtopic_name(subtopic: str) -> str:
    return re.sub(r"\s+", " ", subtopic.strip())


def _normalized_key(subtopic: str) -> str:
    return normalize_subtopic_name(subtopic).casefold()


def current_study_plan_or_error(session: Session, *, user: User, today: dt.date) -> StudyPlan:
    plan = plan_for_date(session, user.id, today)
    if plan is None:
        raise ValueError("No current study-plan week is active. Use /learning-setting to build a plan.")
    return plan


def add_current_subtopic(
    session: Session,
    *,
    user: User,
    subtopic: str,
    today: dt.date,
) -> tuple[StudyPlan, bool, str]:
    clean_subtopic = normalize_subtopic_name(subtopic)
    if not clean_subtopic:
        raise ValueError("Sub-topic cannot be empty.")

    plan = current_study_plan_or_error(session, user=user, today=today)
    existing = list(plan.subtopics or [])
    if any(_normalized_key(item) == _normalized_key(clean_subtopic) for item in existing):
        return plan, False, clean_subtopic
    if len(existing) >= MAX_SUBTOPICS_PER_PLAN:
        raise ValueError(f"A study-plan week can have at most {MAX_SUBTOPICS_PER_PLAN} sub-topics.")

    plan.subtopics = [*existing, clean_subtopic]
    session.flush()
    return plan, True, clean_subtopic


def list_current_subtopics(session: Session, *, user: User, today: dt.date) -> StudyPlan:
    return current_study_plan_or_error(session, user=user, today=today)


def clear_current_subtopics(session: Session, *, user: User, today: dt.date) -> tuple[StudyPlan, int]:
    plan = current_study_plan_or_error(session, user=user, today=today)
    count = len(plan.subtopics or [])
    plan.subtopics = []
    session.flush()
    return plan, count
