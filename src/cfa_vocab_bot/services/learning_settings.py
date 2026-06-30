from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import StudyPlan, SystemEvent, TopicLearningSetting, User, utc_now
from cfa_vocab_bot.services.importers import next_plan_after, plan_for_date

MAX_TOPIC_LEARNING_WEEKS = 52
PLAN_ALERT_EVENT = "study_plan_extension_alert_sent"


def normalize_topic_name(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip().casefold())


def set_topic_learning_weeks(
    session: Session,
    *,
    user: User,
    topic: str,
    weeks: int,
) -> TopicLearningSetting:
    topic = re.sub(r"\s+", " ", topic.strip())
    if not topic:
        raise ValueError("Topic cannot be empty.")
    if weeks < 1 or weeks > MAX_TOPIC_LEARNING_WEEKS:
        raise ValueError(f"Weeks must be between 1 and {MAX_TOPIC_LEARNING_WEEKS}.")

    normalized_topic = normalize_topic_name(topic)
    setting = session.scalar(
        select(TopicLearningSetting).where(
            TopicLearningSetting.user_id == user.id,
            TopicLearningSetting.normalized_topic == normalized_topic,
        )
    )
    if setting is None:
        setting = TopicLearningSetting(
            user_id=user.id,
            topic=topic,
            normalized_topic=normalized_topic,
            weeks=weeks,
        )
        session.add(setting)
    else:
        setting.topic = topic
        setting.weeks = weeks
    session.flush()
    return setting


def list_topic_learning_settings(session: Session, *, user: User) -> list[TopicLearningSetting]:
    return list(
        session.scalars(
            select(TopicLearningSetting)
            .where(TopicLearningSetting.user_id == user.id)
            .order_by(TopicLearningSetting.topic.asc())
        )
    )


def week_start_for(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def append_topic_to_study_plan(
    session: Session,
    *,
    user: User,
    topic: str,
    weeks: int,
    today: dt.date,
) -> list[StudyPlan]:
    setting = set_topic_learning_weeks(session, user=user, topic=topic, weeks=weeks)
    last_plan = session.scalar(
        select(StudyPlan)
        .where(StudyPlan.user_id == user.id)
        .order_by(StudyPlan.end_date.desc(), StudyPlan.week_number.desc())
    )
    start_date = last_plan.end_date + dt.timedelta(days=1) if last_plan else week_start_for(today)
    week_number = (last_plan.week_number + 1) if last_plan else 1
    plans: list[StudyPlan] = []
    for offset in range(setting.weeks):
        row_start = start_date + dt.timedelta(days=offset * 7)
        plan = StudyPlan(
            user_id=user.id,
            week_number=week_number + offset,
            start_date=row_start,
            end_date=row_start + dt.timedelta(days=6),
            main_topic=setting.topic,
            subtopics=[],
            learning_objectives=[f"Study CFA Level I vocabulary for {setting.topic}."],
            reading_or_module_name=setting.topic,
            exam_phase="learning",
            source="learning_setting",
        )
        session.add(plan)
        plans.append(plan)
    session.flush()
    return plans


def list_user_study_plan(session: Session, *, user: User) -> list[StudyPlan]:
    return list(
        session.scalars(
            select(StudyPlan)
            .where(StudyPlan.user_id == user.id)
            .order_by(StudyPlan.start_date.asc(), StudyPlan.week_number.asc())
        )
    )


def reset_user_study_plan(session: Session, *, user: User) -> tuple[int, int]:
    plan_count = len(list_user_study_plan(session, user=user))
    setting_count = len(list_topic_learning_settings(session, user=user))
    session.execute(delete(StudyPlan).where(StudyPlan.user_id == user.id))
    session.execute(delete(TopicLearningSetting).where(TopicLearningSetting.user_id == user.id))
    session.execute(
        delete(SystemEvent).where(
            SystemEvent.user_id == user.id,
            SystemEvent.event_type == PLAN_ALERT_EVENT,
        )
    )
    session.flush()
    return plan_count, setting_count


def _same_topic(left: str, right: str) -> bool:
    return normalize_topic_name(left) == normalize_topic_name(right)


def _resequence_future_plans(
    plans: list[StudyPlan],
    *,
    start_date: dt.date,
    start_week_number: int,
) -> None:
    cursor = start_date
    for index, plan in enumerate(plans):
        duration_days = max(1, (plan.end_date - plan.start_date).days + 1)
        plan.week_number = start_week_number + index
        plan.start_date = cursor
        plan.end_date = cursor + dt.timedelta(days=duration_days - 1)
        cursor = plan.end_date + dt.timedelta(days=1)


def skip_current_topic_remainder(
    session: Session,
    *,
    user: User,
    today: dt.date,
) -> tuple[StudyPlan, int, StudyPlan | None]:
    current = plan_for_date(session, user.id, today)
    if current is None:
        raise ValueError("No current study-plan week is active. Use /learning-setting to build a plan.")
    future = list(
        session.scalars(
            select(StudyPlan)
            .where(StudyPlan.user_id == user.id, StudyPlan.start_date > current.end_date)
            .order_by(StudyPlan.start_date.asc(), StudyPlan.week_number.asc())
        )
    )
    to_delete: list[StudyPlan] = []
    for plan in future:
        if _same_topic(plan.main_topic, current.main_topic):
            to_delete.append(plan)
        else:
            break
    for plan in to_delete:
        session.delete(plan)
    remaining = [plan for plan in future if plan not in to_delete]
    _resequence_future_plans(
        remaining,
        start_date=current.end_date + dt.timedelta(days=1),
        start_week_number=current.week_number + 1,
    )
    session.flush()
    next_plan = remaining[0] if remaining else None
    return current, len(to_delete), next_plan


def study_plan_extension_alert_message(
    session: Session,
    *,
    user: User,
    today: dt.date,
) -> str | None:
    current = plan_for_date(session, user.id, today)
    if current is None:
        return None
    days_left = (current.end_date - today).days
    if days_left < 0 or days_left > 2:
        return None
    if next_plan_after(session, user.id, today) is not None:
        return None
    already_sent = session.scalars(
        select(SystemEvent).where(
            SystemEvent.user_id == user.id,
            SystemEvent.event_type == PLAN_ALERT_EVENT,
        )
    ).all()
    if any(event.payload.get("study_plan_id") == current.id for event in already_sent):
        return None
    day_word = "day" if days_left == 1 else "days"
    if days_left == 0:
        timing = "Your current study-plan topic ends today"
    else:
        timing = f"Your current study-plan topic ends in {days_left} {day_word}"
    return (
        f"{timing}: {current.main_topic}.\n"
        "No topic is planned for next week yet. Use /learning-setting <topic> <weeks> "
        "to extend your study_plan."
    )


def record_study_plan_extension_alert(
    session: Session,
    *,
    user: User,
    current_plan: StudyPlan,
    today: dt.date,
) -> None:
    session.add(
        SystemEvent(
            user_id=user.id,
            event_type=PLAN_ALERT_EVENT,
            payload={"study_plan_id": current_plan.id, "date": today.isoformat()},
            created_at=utc_now(),
        )
    )
    session.flush()
