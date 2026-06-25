from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cfa_vocab_bot.config import Settings
from cfa_vocab_bot.models import User, UserSettings


def ensure_user(
    session: Session,
    *,
    chat_id: int,
    telegram_user_id: int | None,
    username: str | None = None,
    first_name: str | None = None,
    settings: Settings | None = None,
) -> User:
    settings = settings or Settings()
    user = session.scalar(select(User).where(User.chat_id == chat_id))
    if user is None and telegram_user_id is not None:
        user = session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
    if user is None:
        user = User(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            is_admin=telegram_user_id in settings.admin_user_ids if telegram_user_id else False,
        )
        user.settings = UserSettings(
            timezone=settings.default_timezone,
            daily_send_time=settings.default_daily_send_time,
            mini_review_time=settings.default_mini_review_time,
            weekly_quiz_time=settings.default_weekly_quiz_time,
            weekly_recap_time=settings.default_weekly_recap_time,
        )
        session.add(user)
        session.flush()
        return user

    user.username = username or user.username
    user.first_name = first_name or user.first_name
    user.telegram_user_id = telegram_user_id or user.telegram_user_id
    if user.settings is None:
        user.settings = UserSettings(
            timezone=settings.default_timezone,
            daily_send_time=settings.default_daily_send_time,
            mini_review_time=settings.default_mini_review_time,
            weekly_quiz_time=settings.default_weekly_quiz_time,
            weekly_recap_time=settings.default_weekly_recap_time,
        )
    return user


def get_user_by_chat_id(session: Session, chat_id: int) -> User | None:
    return session.scalar(select(User).where(User.chat_id == chat_id))

