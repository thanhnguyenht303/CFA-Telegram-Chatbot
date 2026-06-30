from __future__ import annotations

import datetime as dt

import pytest

from cfa_vocab_bot.services.importers import import_timeline
from cfa_vocab_bot.services.subtopics import (
    add_current_subtopic,
    clear_current_subtopics,
    list_current_subtopics,
)
from cfa_vocab_bot.telegram.formatters import format_current_subtopics


def test_add_list_and_clear_current_subtopics(session, user, current_week_csv):
    import_timeline(session, user_id=user.id, path=current_week_csv)
    session.commit()

    plan, added, clean = add_current_subtopic(
        session,
        user=user,
        subtopic=" Time Value   of Money ",
        today=dt.date(2026, 6, 24),
    )
    duplicate_plan, duplicate_added, _clean = add_current_subtopic(
        session,
        user=user,
        subtopic="time value of money",
        today=dt.date(2026, 6, 24),
    )
    session.commit()

    assert added is True
    assert clean == "Time Value of Money"
    assert duplicate_plan.id == plan.id
    assert duplicate_added is False
    assert list_current_subtopics(
        session, user=user, today=dt.date(2026, 6, 24)
    ).subtopics == ["cash flow", "ratios", "Time Value of Money"]

    cleared_plan, count = clear_current_subtopics(
        session,
        user=user,
        today=dt.date(2026, 6, 24),
    )
    session.commit()

    assert cleared_plan.id == plan.id
    assert count == 3
    assert cleared_plan.subtopics == []


def test_subtopic_commands_require_active_plan(session, user):
    with pytest.raises(ValueError, match="No current study-plan week"):
        add_current_subtopic(
            session,
            user=user,
            subtopic="Probability",
            today=dt.date(2026, 6, 24),
        )


def test_format_current_subtopics():
    class Plan:
        week_number = 1
        main_topic = "Quantitative Methods"
        subtopics = ["Time Value of Money", "Probability"]

    message = format_current_subtopics(Plan())

    assert "Sub-topics for Week 1: Quantitative Methods" in message
    assert "- Time Value of Money" in message
    assert "- Probability" in message
