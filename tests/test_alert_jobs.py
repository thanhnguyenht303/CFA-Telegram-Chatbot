from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from cfa_vocab_bot import jobs
from cfa_vocab_bot.jobs import (
    send_daily_vocab_job,
    send_mini_review_job,
    send_plan_alert_job,
    send_weekly_quiz_job,
    send_weekly_recap_job,
)
from cfa_vocab_bot.models import DeliveryLog, QuizQuestion, QuizResult, ReviewState, SchedulerJob
from cfa_vocab_bot.scheduler import schedule_user_jobs
from cfa_vocab_bot.services.content_engine import record_vocab_delivery, select_daily_vocab
from cfa_vocab_bot.services.importers import import_timeline
from cfa_vocab_bot.services.learning_settings import append_topic_to_study_plan


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_message(self, *args, **kwargs):
        message = dict(kwargs)
        if args:
            message.setdefault("chat_id", args[0])
        if len(args) > 1:
            message.setdefault("text", args[1])
        self.messages.append(message)
        return SimpleNamespace(message_id=len(self.messages))


def _import_current_week(session, user, current_week_csv) -> None:
    count, warnings = import_timeline(session, user_id=user.id, path=current_week_csv)
    assert count == 1
    assert warnings == []
    session.commit()


def _job_count(session, job_type: str, status: str) -> int:
    return int(
        session.scalar(
            select(func.count(SchedulerJob.id)).where(
                SchedulerJob.job_type == job_type,
                SchedulerJob.status == status,
            )
        )
        or 0
    )


def test_schedule_user_jobs_registers_expected_alert_times(session_factory, user):
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))

    schedule_user_jobs(scheduler, session_factory, FakeBot(), user)

    expected_ids = {
        f"user:{user.id}:daily_vocab",
        f"user:{user.id}:mini_review",
        f"user:{user.id}:plan_alert",
        f"user:{user.id}:weekly_quiz",
        f"user:{user.id}:weekly_recap",
    }
    assert {job.id for job in scheduler.get_jobs()} == expected_ids

    base = dt.datetime(2026, 6, 26, 12, 0, tzinfo=dt.UTC)
    assert scheduler.get_job(f"user:{user.id}:daily_vocab").trigger.get_next_fire_time(
        None, base
    ).astimezone(dt.UTC) == dt.datetime(2026, 6, 26, 12, 30, tzinfo=dt.UTC)
    assert scheduler.get_job(f"user:{user.id}:plan_alert").trigger.get_next_fire_time(
        None, base
    ).astimezone(dt.UTC) == dt.datetime(2026, 6, 26, 12, 30, tzinfo=dt.UTC)
    assert scheduler.get_job(f"user:{user.id}:mini_review").trigger.get_next_fire_time(
        None, base
    ).astimezone(dt.UTC) == dt.datetime(2026, 6, 27, 2, 40, tzinfo=dt.UTC)
    assert scheduler.get_job(f"user:{user.id}:weekly_quiz").trigger.get_next_fire_time(
        None, base
    ).astimezone(dt.UTC) == dt.datetime(2026, 6, 27, 14, 0, tzinfo=dt.UTC)
    assert scheduler.get_job(f"user:{user.id}:weekly_recap").trigger.get_next_fire_time(
        None, base
    ).astimezone(dt.UTC) == dt.datetime(2026, 6, 28, 23, 30, tzinfo=dt.UTC)


def test_schedule_user_jobs_replaces_and_removes_runtime_jobs(session_factory, user):
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
    schedule_user_jobs(scheduler, session_factory, FakeBot(), user)

    user.settings.daily_send_time = dt.time(8, 15)
    schedule_user_jobs(scheduler, session_factory, FakeBot(), user)

    base = dt.datetime(2026, 6, 26, 12, 0, tzinfo=dt.UTC)
    next_daily = scheduler.get_job(f"user:{user.id}:daily_vocab").trigger.get_next_fire_time(
        None, base
    )
    assert next_daily.astimezone(dt.UTC) == dt.datetime(2026, 6, 26, 13, 15, tzinfo=dt.UTC)
    assert len(scheduler.get_jobs()) == 5

    user.paused = True
    schedule_user_jobs(scheduler, session_factory, FakeBot(), user)
    assert scheduler.get_jobs() == []


@pytest.mark.asyncio
async def test_daily_vocab_job_sends_and_records_delivery(
    session_factory,
    session,
    user,
    seeded,
    current_week_csv,
    monkeypatch,
):
    _import_current_week(session, user, current_week_csv)
    monkeypatch.setattr(jobs, "utc_now", lambda: dt.datetime(2026, 6, 24, 12, 30, tzinfo=dt.UTC))
    bot = FakeBot()

    await send_daily_vocab_job(user.id, session_factory, bot)

    assert len(bot.messages) == 1
    assert "CFA Vocab" in str(bot.messages[0]["text"])
    delivered = session.scalar(
        select(func.count(DeliveryLog.id)).where(DeliveryLog.delivery_type == "daily_vocab")
    )
    assert delivered == user.settings.daily_vocab_count
    assert _job_count(session, "daily_vocab", "sent") == 1


@pytest.mark.asyncio
async def test_mini_review_job_uses_user_local_day_for_evening_alert(
    session_factory,
    session,
    user,
    seeded,
    current_week_csv,
    monkeypatch,
):
    _import_current_week(session, user, current_week_csv)
    plan, vocab_items = select_daily_vocab(
        session,
        user,
        today=dt.date(2026, 6, 24),
        count=3,
    )
    record_vocab_delivery(
        session,
        user=user,
        vocab_items=vocab_items,
        delivery_type="daily_vocab",
        plan=plan,
        sent_at=dt.datetime(2026, 6, 24, 12, 30, tzinfo=dt.UTC),
    )
    for state in session.scalars(select(ReviewState).where(ReviewState.user_id == user.id)):
        state.next_review_at = dt.datetime(2026, 6, 30, tzinfo=dt.UTC)
    session.commit()
    monkeypatch.setattr(jobs, "utc_now", lambda: dt.datetime(2026, 6, 25, 2, 40, tzinfo=dt.UTC))
    bot = FakeBot()

    await send_mini_review_job(user.id, session_factory, bot)

    assert len(bot.messages) == 1
    assert "Mini review - quick recall" in str(bot.messages[0]["text"])
    local_day_indexes = session.scalars(
        select(DeliveryLog.day_index).where(DeliveryLog.delivery_type == "mini_review")
    ).all()
    assert set(local_day_indexes) == {2}
    assert _job_count(session, "mini_review", "sent") == 1


@pytest.mark.asyncio
async def test_weekly_quiz_job_sends_first_question_and_logs(
    session_factory,
    session,
    user,
    seeded,
    current_week_csv,
    monkeypatch,
):
    _import_current_week(session, user, current_week_csv)
    monkeypatch.setattr(jobs, "utc_now", lambda: dt.datetime(2026, 6, 27, 14, 0, tzinfo=dt.UTC))
    bot = FakeBot()

    await send_weekly_quiz_job(user.id, session_factory, bot)

    assert len(bot.messages) == 1
    assert "Weekly CFA Vocab Quiz" in str(bot.messages[0]["text"])
    quiz = session.scalar(select(QuizResult).where(QuizResult.user_id == user.id))
    assert quiz is not None
    assert session.scalar(select(func.count(QuizQuestion.id))) == quiz.total_questions
    assert _job_count(session, "weekly_quiz", "sent") == 1


@pytest.mark.asyncio
async def test_weekly_recap_job_sends_recap_and_logs(
    session_factory,
    session,
    user,
    seeded,
    current_week_csv,
    monkeypatch,
):
    _import_current_week(session, user, current_week_csv)
    monkeypatch.setattr(jobs, "utc_now", lambda: dt.datetime(2026, 6, 28, 23, 30, tzinfo=dt.UTC))
    bot = FakeBot()

    await send_weekly_recap_job(user.id, session_factory, bot)

    assert len(bot.messages) == 1
    assert "Weekly CFA Vocab Recap" in str(bot.messages[0]["text"])
    assert _job_count(session, "weekly_recap", "sent") == 1


@pytest.mark.asyncio
async def test_plan_alert_job_sends_once_when_current_plan_has_no_next_week(
    session_factory,
    session,
    user,
    monkeypatch,
):
    append_topic_to_study_plan(
        session,
        user=user,
        topic="Quantitative Methods",
        weeks=1,
        today=dt.date(2026, 6, 22),
    )
    session.commit()
    monkeypatch.setattr(jobs, "utc_now", lambda: dt.datetime(2026, 6, 26, 12, 30, tzinfo=dt.UTC))
    bot = FakeBot()

    await send_plan_alert_job(user.id, session_factory, bot)
    await send_plan_alert_job(user.id, session_factory, bot)

    assert len(bot.messages) == 1
    assert "No topic is planned for next week yet" in str(bot.messages[0]["text"])
    assert _job_count(session, "plan_alert", "sent") == 1
    assert _job_count(session, "plan_alert", "skipped") == 1
