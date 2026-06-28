from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from cfa_vocab_bot.models import UserSettings


def local_date(settings: UserSettings, now: dt.datetime) -> dt.date:
    return now.astimezone(ZoneInfo(settings.timezone)).date()


def can_send_now(settings: UserSettings, now: dt.datetime) -> bool:
    if settings.quiet_hours_start is None or settings.quiet_hours_end is None:
        return True
    local_now = now.astimezone(ZoneInfo(settings.timezone)).time()
    start = settings.quiet_hours_start
    end = settings.quiet_hours_end
    if start < end:
        return not (start <= local_now < end)
    return not (local_now >= start or local_now < end)


def exam_phase_for_date(exam_date: dt.date | None, today: dt.date | None = None) -> str:
    if exam_date is None:
        return "learning"
    today = today or dt.date.today()
    days = (exam_date - today).days
    if days <= 7:
        return "final_week"
    if days <= 21:
        return "final_review"
    if days <= 56:
        return "mock_review"
    if days <= 120:
        return "consolidation"
    return "learning"
