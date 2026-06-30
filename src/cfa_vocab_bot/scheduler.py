from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cfa_vocab_bot.jobs import (
    send_daily_vocab_job,
    send_mini_review_job,
    send_plan_alert_job,
    send_weekly_quiz_job,
    send_weekly_recap_job,
)
from cfa_vocab_bot.models import User

ALERT_JOB_TYPES = ("daily_vocab", "mini_review", "weekly_quiz", "weekly_recap", "plan_alert")


def _cron_for_time(*, timezone: str, at: dt.time, day_of_week: str | int | None = None) -> CronTrigger:
    kwargs = {
        "hour": at.hour,
        "minute": at.minute,
        "timezone": ZoneInfo(timezone),
    }
    if day_of_week is not None:
        kwargs["day_of_week"] = day_of_week
    return CronTrigger(**kwargs)


def _user_job_id(user_id: int, job_type: str) -> str:
    return f"user:{user_id}:{job_type}"


def remove_user_jobs(scheduler: AsyncIOScheduler, user_id: int) -> None:
    for job_type in ALERT_JOB_TYPES:
        job_id = _user_job_id(user_id, job_type)
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)


def schedule_user_jobs(
    scheduler: AsyncIOScheduler,
    session_factory: sessionmaker[Session],
    telegram_bot,
    user: User,
) -> None:
    settings = user.settings
    if not user.is_active or user.paused:
        remove_user_jobs(scheduler, user.id)
        return
    remove_user_jobs(scheduler, user.id)
    scheduler.add_job(
        send_daily_vocab_job,
        _cron_for_time(timezone=settings.timezone, at=settings.daily_send_time, day_of_week="mon-fri"),
        id=_user_job_id(user.id, "daily_vocab"),
        replace_existing=True,
        kwargs={"user_id": user.id, "session_factory": session_factory, "telegram_bot": telegram_bot},
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_mini_review_job,
        _cron_for_time(timezone=settings.timezone, at=settings.mini_review_time, day_of_week="mon-fri"),
        id=_user_job_id(user.id, "mini_review"),
        replace_existing=True,
        kwargs={"user_id": user.id, "session_factory": session_factory, "telegram_bot": telegram_bot},
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_weekly_quiz_job,
        _cron_for_time(
            timezone=settings.timezone,
            at=settings.weekly_quiz_time,
            day_of_week=settings.weekly_quiz_day,
        ),
        id=_user_job_id(user.id, "weekly_quiz"),
        replace_existing=True,
        kwargs={"user_id": user.id, "session_factory": session_factory, "telegram_bot": telegram_bot},
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_weekly_recap_job,
        _cron_for_time(
            timezone=settings.timezone,
            at=settings.weekly_recap_time,
            day_of_week=settings.weekly_recap_day,
        ),
        id=_user_job_id(user.id, "weekly_recap"),
        replace_existing=True,
        kwargs={"user_id": user.id, "session_factory": session_factory, "telegram_bot": telegram_bot},
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_plan_alert_job,
        _cron_for_time(timezone=settings.timezone, at=settings.daily_send_time),
        id=_user_job_id(user.id, "plan_alert"),
        replace_existing=True,
        kwargs={"user_id": user.id, "session_factory": session_factory, "telegram_bot": telegram_bot},
        max_instances=1,
        coalesce=True,
    )


def build_scheduler(
    session_factory: sessionmaker[Session],
    telegram_bot,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
    with session_factory() as session:
        users = session.scalars(select(User).where(User.is_active.is_(True))).all()
        for user in users:
            schedule_user_jobs(scheduler, session_factory, telegram_bot, user)
    return scheduler
