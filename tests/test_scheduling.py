from __future__ import annotations

import datetime as dt

from cfa_vocab_bot.services.scheduling import can_send_now, exam_phase_for_date


def test_quiet_hours_support_overnight(user):
    user.settings.quiet_hours_start = dt.time(22, 0)
    user.settings.quiet_hours_end = dt.time(7, 0)
    user.settings.timezone = "America/Chicago"
    quiet = dt.datetime(2026, 6, 25, 4, 0, tzinfo=dt.UTC)
    allowed = dt.datetime(2026, 6, 25, 14, 0, tzinfo=dt.UTC)
    assert can_send_now(user.settings, quiet) is False
    assert can_send_now(user.settings, allowed) is True


def test_exam_phase_changes_near_exam_date():
    today = dt.date(2026, 6, 24)
    assert exam_phase_for_date(dt.date(2026, 12, 24), today) == "learning"
    assert exam_phase_for_date(dt.date(2026, 10, 1), today) == "consolidation"
    assert exam_phase_for_date(dt.date(2026, 8, 1), today) == "mock_review"
    assert exam_phase_for_date(dt.date(2026, 7, 10), today) == "final_review"
    assert exam_phase_for_date(dt.date(2026, 6, 30), today) == "final_week"

