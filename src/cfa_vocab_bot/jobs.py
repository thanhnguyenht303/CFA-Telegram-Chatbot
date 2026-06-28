from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cfa_vocab_bot.models import SchedulerJob, User, utc_now
from cfa_vocab_bot.services.content_engine import (
    record_vocab_delivery,
    select_daily_vocab,
    terms_due_for_mini_review,
    weak_vocab,
)
from cfa_vocab_bot.services.scheduling import can_send_now, local_date
from cfa_vocab_bot.services.progress import progress_snapshot
from cfa_vocab_bot.services.quiz import create_weekly_quiz, next_unanswered_question
from cfa_vocab_bot.telegram.formatters import (
    format_daily_vocab,
    format_mini_review,
    format_quiz_question,
    format_weekly_recap,
)
from cfa_vocab_bot.telegram.keyboards import vocab_keyboard, quiz_keyboard

logger = logging.getLogger(__name__)


def _get_user(session: Session, user_id: int) -> User | None:
    return session.scalar(select(User).where(User.id == user_id))


async def _log_job(
    session: Session,
    user_id: int,
    job_type: str,
    status: str,
    error: str | None = None,
) -> None:
    session.add(
        SchedulerJob(
            user_id=user_id,
            job_type=job_type,
            scheduled_at=utc_now(),
            status=status,
            last_error=error,
        )
    )


async def send_daily_vocab_job(user_id: int, session_factory: sessionmaker[Session], telegram_bot) -> None:
    with session_factory() as session:
        user = _get_user(session, user_id)
        now = utc_now()
        if user is None or user.paused or not can_send_now(user.settings, now):
            return
        try:
            plan, vocab_items = select_daily_vocab(
                session,
                user,
                today=local_date(user.settings, now),
            )
            if not vocab_items:
                await telegram_bot.send_message(user.chat_id, "No approved vocab is available today.")
                await _log_job(session, user.id, "daily_vocab", "skipped")
            else:
                message = format_daily_vocab(plan, vocab_items)
                sent = await telegram_bot.send_message(
                    chat_id=user.chat_id,
                    text=message,
                    reply_markup=vocab_keyboard(vocab_items),
                    disable_web_page_preview=True,
                )
                record_vocab_delivery(
                    session,
                    user=user,
                    vocab_items=vocab_items,
                    delivery_type="daily_vocab",
                    plan=plan,
                    message_id=getattr(sent, "message_id", None),
                    sent_at=now,
                )
                await _log_job(session, user.id, "daily_vocab", "sent")
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("Daily vocab job failed for user_id=%s", user_id)
            await _log_job(session, user_id, "daily_vocab", "failed", str(exc))
            session.commit()


async def send_mini_review_job(user_id: int, session_factory: sessionmaker[Session], telegram_bot) -> None:
    with session_factory() as session:
        user = _get_user(session, user_id)
        now = utc_now()
        if user is None or user.paused or not can_send_now(user.settings, now):
            return
        try:
            vocab_items = terms_due_for_mini_review(session, user, now=now)
            if vocab_items:
                await telegram_bot.send_message(
                    chat_id=user.chat_id,
                    text=format_mini_review(vocab_items),
                    reply_markup=vocab_keyboard(vocab_items),
                )
                record_vocab_delivery(
                    session,
                    user=user,
                    vocab_items=vocab_items,
                    delivery_type="mini_review",
                    sent_at=now,
                )
            await _log_job(session, user.id, "mini_review", "sent" if vocab_items else "skipped")
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("Mini review job failed for user_id=%s", user_id)
            await _log_job(session, user_id, "mini_review", "failed", str(exc))
            session.commit()


async def send_weekly_quiz_job(user_id: int, session_factory: sessionmaker[Session], telegram_bot) -> None:
    with session_factory() as session:
        user = _get_user(session, user_id)
        now = utc_now()
        if user is None or user.paused or not can_send_now(user.settings, now):
            return
        try:
            quiz = create_weekly_quiz(session, user, today=local_date(user.settings, now))
            question = next_unanswered_question(session, user, quiz)
            if question:
                await telegram_bot.send_message(
                    chat_id=user.chat_id,
                    text=format_quiz_question(question, quiz),
                    reply_markup=quiz_keyboard(quiz.id, question),
                )
            await _log_job(session, user.id, "weekly_quiz", "sent")
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("Weekly quiz job failed for user_id=%s", user_id)
            await _log_job(session, user_id, "weekly_quiz", "failed", str(exc))
            session.commit()


async def send_weekly_recap_job(user_id: int, session_factory: sessionmaker[Session], telegram_bot) -> None:
    with session_factory() as session:
        user = _get_user(session, user_id)
        now = utc_now()
        if user is None or user.paused or not can_send_now(user.settings, now):
            return
        try:
            snapshot = progress_snapshot(session, user, today=local_date(user.settings, now))
            weak = weak_vocab(session, user, limit=10)
            await telegram_bot.send_message(
                chat_id=user.chat_id,
                text=format_weekly_recap(snapshot, weak),
            )
            await _log_job(session, user.id, "weekly_recap", "sent")
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("Weekly recap job failed for user_id=%s", user_id)
            await _log_job(session, user_id, "weekly_recap", "failed", str(exc))
            session.commit()
