from __future__ import annotations

import pytest
from sqlalchemy import select

from cfa_vocab_bot.models import StudyPlan, SystemEvent
from cfa_vocab_bot.services.learning_settings import (
    PLAN_ALERT_EVENT,
    append_topic_to_study_plan,
    list_topic_learning_settings,
    list_user_study_plan,
    normalize_topic_name,
    reset_user_study_plan,
    set_topic_learning_weeks,
    skip_current_topic_remainder,
)
from cfa_vocab_bot.telegram.formatters import format_learning_settings, format_study_plan
from cfa_vocab_bot.telegram.handlers import _parse_learning_setting_args


def test_set_topic_learning_weeks_creates_and_updates_by_normalized_topic(session, user):
    setting = set_topic_learning_weeks(
        session,
        user=user,
        topic="Fixed Income",
        weeks=3,
    )
    session.commit()

    assert setting.topic == "Fixed Income"
    assert setting.weeks == 3
    assert normalize_topic_name(" fixed   income ") == "fixed income"

    updated = set_topic_learning_weeks(
        session,
        user=user,
        topic=" fixed   income ",
        weeks=4,
    )
    session.commit()

    settings = list_topic_learning_settings(session, user=user)
    assert len(settings) == 1
    assert updated.id == setting.id
    assert settings[0].topic == "fixed income"
    assert settings[0].weeks == 4


def test_set_topic_learning_weeks_validates_range(session, user):
    with pytest.raises(ValueError, match="between 1 and 52"):
        set_topic_learning_weeks(session, user=user, topic="Ethics", weeks=0)

    with pytest.raises(ValueError, match="between 1 and 52"):
        set_topic_learning_weeks(session, user=user, topic="Ethics", weeks=53)


def test_format_learning_settings():
    class Setting:
        topic = "Ethics"
        weeks = 1

    message = format_learning_settings([Setting()])

    assert "Topic learning settings" in message
    assert "- Ethics: 1 week" in message
    assert "/learning-setting" in format_learning_settings([])


def test_parse_learning_setting_args():
    assert _parse_learning_setting_args(["Fixed", "Income", "3"]) == ("Fixed Income", 3)
    assert _parse_learning_setting_args([]) is None

    with pytest.raises(ValueError, match="last argument"):
        _parse_learning_setting_args(["Fixed", "Income", "three"])


def test_append_topic_to_study_plan_builds_continuous_weekly_rows(session, user):
    first = append_topic_to_study_plan(
        session,
        user=user,
        topic="Quantitative Methods",
        weeks=2,
        today=__import__("datetime").date(2026, 6, 29),
    )
    second = append_topic_to_study_plan(
        session,
        user=user,
        topic="Financial Statement Analysis",
        weeks=3,
        today=__import__("datetime").date(2026, 6, 29),
    )
    third = append_topic_to_study_plan(
        session,
        user=user,
        topic="Standards of Practice",
        weeks=3,
        today=__import__("datetime").date(2026, 6, 29),
    )
    session.commit()

    plans = list_user_study_plan(session, user=user)

    assert len(first) == 2
    assert len(second) == 3
    assert len(third) == 3
    assert len(plans) == 8
    assert [plan.main_topic for plan in plans] == [
        "Quantitative Methods",
        "Quantitative Methods",
        "Financial Statement Analysis",
        "Financial Statement Analysis",
        "Financial Statement Analysis",
        "Standards of Practice",
        "Standards of Practice",
        "Standards of Practice",
    ]
    assert plans[0].start_date.isoformat() == "2026-06-29"
    assert plans[1].start_date.isoformat() == "2026-07-06"
    assert plans[2].start_date.isoformat() == "2026-07-13"
    assert plans[-1].end_date.isoformat() == "2026-08-23"


def test_reset_user_study_plan_clears_plan_and_learning_settings(session, user):
    append_topic_to_study_plan(
        session,
        user=user,
        topic="Ethics",
        weeks=2,
        today=__import__("datetime").date(2026, 6, 29),
    )
    session.add(
        SystemEvent(
            user_id=user.id,
            event_type=PLAN_ALERT_EVENT,
            payload={"study_plan_id": 1},
        )
    )
    session.commit()

    plan_count, setting_count = reset_user_study_plan(session, user=user)
    session.commit()

    assert plan_count == 2
    assert setting_count == 1
    assert list_user_study_plan(session, user=user) == []
    assert list_topic_learning_settings(session, user=user) == []
    assert (
        session.scalar(
            select(SystemEvent).where(
                SystemEvent.user_id == user.id,
                SystemEvent.event_type == PLAN_ALERT_EVENT,
            )
        )
        is None
    )


def test_skip_current_topic_remainder_moves_next_stage_to_next_week(session, user):
    append_topic_to_study_plan(
        session,
        user=user,
        topic="Quantitative Methods",
        weeks=2,
        today=__import__("datetime").date(2026, 6, 29),
    )
    append_topic_to_study_plan(
        session,
        user=user,
        topic="Financial Statement Analysis",
        weeks=2,
        today=__import__("datetime").date(2026, 6, 29),
    )
    session.commit()

    current, removed_count, next_plan = skip_current_topic_remainder(
        session,
        user=user,
        today=__import__("datetime").date(2026, 7, 1),
    )
    session.commit()
    plans = list_user_study_plan(session, user=user)

    assert current.main_topic == "Quantitative Methods"
    assert removed_count == 1
    assert next_plan is not None
    assert next_plan.main_topic == "Financial Statement Analysis"
    assert [plan.main_topic for plan in plans] == [
        "Quantitative Methods",
        "Financial Statement Analysis",
        "Financial Statement Analysis",
    ]
    assert plans[1].week_number == 2
    assert plans[1].start_date.isoformat() == "2026-07-06"
    assert plans[2].week_number == 3
    assert plans[2].start_date.isoformat() == "2026-07-13"


def test_format_study_plan():
    plan = StudyPlan(
        week_number=1,
        start_date=__import__("datetime").date(2026, 6, 29),
        end_date=__import__("datetime").date(2026, 7, 5),
        main_topic="Quantitative Methods",
    )

    message = format_study_plan([plan])

    assert "Current study_plan" in message
    assert "Week 1: Quantitative Methods" in message
    assert "/learning-setting" in format_study_plan([])
