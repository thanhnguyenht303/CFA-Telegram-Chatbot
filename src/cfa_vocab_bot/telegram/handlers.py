from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cfa_vocab_bot.config import Settings
from cfa_vocab_bot.models import QuizQuestion, QuizResult, User, VocabItem, utc_now
from cfa_vocab_bot.scheduler import remove_user_jobs, schedule_user_jobs
from cfa_vocab_bot.services.content_engine import (
    record_vocab_delivery,
    select_daily_vocab,
    select_review_vocab,
    todays_vocab,
    weak_vocab,
)
from cfa_vocab_bot.services.export import export_all_user_data, export_anki_tsv, export_vocab_csv
from cfa_vocab_bot.services.importers import import_timeline
from cfa_vocab_bot.services.learning_settings import (
    append_topic_to_study_plan,
    list_user_study_plan,
    reset_user_study_plan,
    skip_current_topic_remainder,
)
from cfa_vocab_bot.services.privacy import delete_user_data
from cfa_vocab_bot.services.progress import format_progress, progress_snapshot
from cfa_vocab_bot.services.quiz import (
    active_quiz,
    create_weekly_quiz,
    grade_answer,
    next_unanswered_question,
    quiz_feedback,
)
from cfa_vocab_bot.services.research import (
    MAX_RESEARCH_NUMBER,
    ResearchUnavailable,
    approve_research_suggestion,
    provider_from_settings,
    reject_research_suggestion,
    research_topic,
)
from cfa_vocab_bot.services.spaced_repetition import apply_review_result, get_or_create_review_state
from cfa_vocab_bot.services.subtopics import (
    add_current_subtopic,
    clear_current_subtopics,
    list_current_subtopics,
)
from cfa_vocab_bot.services.topics import available_topic_counts, resolve_topic_for_learning
from cfa_vocab_bot.services.users import ensure_user, get_user_by_chat_id
from cfa_vocab_bot.telegram.formatters import (
    format_appended_study_plan,
    format_available_topics,
    format_current_subtopics,
    format_daily_vocab,
    format_mini_review,
    format_quiz_question,
    format_research_suggestions,
    format_start_welcome,
    format_study_plan,
    format_topic_validation_error,
)
from cfa_vocab_bot.telegram.keyboards import quiz_keyboard, research_keyboard, vocab_keyboard

COMMANDS = [
    BotCommand("start", "Activate the bot"),
    BotCommand("today", "Show today's vocab"),
    BotCommand("review", "Review due vocab"),
    BotCommand("quiz", "Start the weekly quiz now"),
    BotCommand("progress", "Show learning progress"),
    BotCommand("weak", "Show weak words"),
    BotCommand("topic", "Show current CFA topic"),
    BotCommand("topics_display", "Show vocab topics in the pool"),
    BotCommand("learning_setting", "Set weeks needed for a topic"),
    BotCommand("subtopic_add", "Add current week sub-topic"),
    BotCommand("subtopic_list", "List current week sub-topics"),
    BotCommand("subtopic_clear", "Clear current week sub-topics"),
    BotCommand("nextweek", "Preview next topic"),
    BotCommand("reset", "Clear your study plan"),
    BotCommand("skip", "Skip remaining future weeks of current topic"),
    BotCommand("pause", "Pause scheduled messages"),
    BotCommand("resume", "Resume scheduled messages"),
    BotCommand("settings", "Change schedule and preferences"),
    BotCommand("export", "Export CSV or Anki TSV"),
    BotCommand("research", "Research CFA vocab suggestions"),
    BotCommand("export_my_data", "Export all personal data"),
    BotCommand("delete_my_data", "Delete personal data"),
    BotCommand("error", "Add terms from an error log"),
]


def _session_factory(context: ContextTypes.DEFAULT_TYPE) -> sessionmaker[Session]:
    return context.application.bot_data["session_factory"]


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def _sync_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    scheduler = context.application.bot_data.get("scheduler")
    if scheduler is None:
        return
    schedule_user_jobs(scheduler, _session_factory(context), context.application.bot, user)


def _remove_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    scheduler = context.application.bot_data.get("scheduler")
    if scheduler is not None:
        remove_user_jobs(scheduler, user_id)


def _chat_id(update: Update) -> int:
    if update.effective_chat is None:
        raise RuntimeError("Update has no chat.")
    return update.effective_chat.id


def _ensure_user_from_update(session: Session, update: Update, settings: Settings) -> User:
    tg_user = update.effective_user
    return ensure_user(
        session,
        chat_id=_chat_id(update),
        telegram_user_id=tg_user.id if tg_user else None,
        username=tg_user.username if tg_user else None,
        first_name=tg_user.first_name if tg_user else None,
        settings=settings,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        welcome = format_start_welcome(user)
        session.commit()
        _sync_scheduled_jobs(context, user)
    await update.effective_message.reply_text(welcome)


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        vocab_items = todays_vocab(session, user)
        plan = None
        if not vocab_items:
            plan, vocab_items = select_daily_vocab(session, user)
            record_vocab_delivery(session, user=user, vocab_items=vocab_items, delivery_type="daily_vocab", plan=plan)
        session.commit()
        await update.effective_message.reply_text(
            format_daily_vocab(plan, vocab_items),
            reply_markup=vocab_keyboard(vocab_items),
        )


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        vocab_items = select_review_vocab(session, user, count=10)
        if vocab_items:
            record_vocab_delivery(session, user=user, vocab_items=vocab_items, delivery_type="manual_review")
        session.commit()
        text = format_mini_review(vocab_items) if vocab_items else "No due review terms yet."
        await update.effective_message.reply_text(text, reply_markup=vocab_keyboard(vocab_items))


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        quiz_result = active_quiz(session, user) or create_weekly_quiz(session, user)
        question = next_unanswered_question(session, user, quiz_result)
        session.commit()
        if question is None:
            await update.effective_message.reply_text(quiz_feedback(session, quiz_result))
            return
        await update.effective_message.reply_text(
            format_quiz_question(question, quiz_result),
            reply_markup=quiz_keyboard(quiz_result.id, question),
        )


async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        snapshot = progress_snapshot(session, user)
        await update.effective_message.reply_text(format_progress(snapshot))


async def weak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        rows = weak_vocab(session, user, limit=10)
        if not rows:
            text = "No weak terms yet."
        else:
            text = "Top weak terms:\n" + "\n".join(
                f"- {vocab.term}: wrong={state.wrong_count}, next review={state.next_review_at}"
                for vocab, state in rows
            )
        await update.effective_message.reply_text(text)


async def topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cfa_vocab_bot.services.content_engine import current_plan

    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        plan = current_plan(session, user)
        text = (
            f"Current topic: Week {plan.week_number} - {plan.main_topic}\n"
            f"Subtopics: {', '.join(plan.subtopics) if plan.subtopics else 'n/a'}"
            if plan
            else "No current topic. Upload a timeline CSV/JSON or use /learning-setting <topic> <weeks>."
        )
        await update.effective_message.reply_text(text)


async def topics_display(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        _ensure_user_from_update(session, update, _settings(context))
        text = format_available_topics(available_topic_counts(session))
        session.commit()
        await update.effective_message.reply_text(text)


def _args_from_command_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    if context.args:
        return list(context.args)
    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return []
    return parts[1].split()


def _parse_learning_setting_args(args: list[str]) -> tuple[str, int] | None:
    if not args:
        return None
    if len(args) < 2:
        raise ValueError(
            "Use /learning-setting <topic> <weeks>, for example: "
            "/learning-setting Fixed Income 3"
        )
    try:
        weeks = int(args[-1])
    except ValueError as exc:
        raise ValueError("The last argument must be the number of weeks.") from exc
    topic = " ".join(args[:-1]).strip()
    if not topic:
        raise ValueError("Topic cannot be empty.")
    return topic, weeks


def _parse_subtopic_args(args: list[str]) -> str:
    subtopic = " ".join(args).strip()
    if not subtopic:
        raise ValueError(
            "Use /subtopic-add <subtopic>, for example: /subtopic-add Time Value of Money"
        )
    return subtopic


async def learning_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        parsed = _parse_learning_setting_args(_args_from_command_text(update, context))
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return

    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        if parsed is None:
            text = format_study_plan(list_user_study_plan(session, user=user))
            session.commit()
            await update.effective_message.reply_text(text)
            return
        topic_name, weeks = parsed
        resolution = resolve_topic_for_learning(session, topic_name)
        if not resolution.is_valid:
            await update.effective_message.reply_text(
                format_topic_validation_error(
                    topic=topic_name,
                    weeks=weeks,
                    suggestion=resolution.suggestion,
                    available_topics=resolution.available_topics,
                )
            )
            return
        try:
            plans = append_topic_to_study_plan(
                session,
                user=user,
                topic=resolution.topic or topic_name,
                weeks=weeks,
                today=dt.datetime.now(ZoneInfo(user.settings.timezone)).date(),
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return
        session.commit()
    await update.effective_message.reply_text(
        format_appended_study_plan(resolution.topic or topic_name, plans)
    )


async def subtopic_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        subtopic_text = _parse_subtopic_args(_args_from_command_text(update, context))
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return

    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        today = dt.datetime.now(ZoneInfo(user.settings.timezone)).date()
        try:
            plan, added, clean_subtopic = add_current_subtopic(
                session,
                user=user,
                subtopic=subtopic_text,
                today=today,
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return
        session.commit()
    if added:
        await update.effective_message.reply_text(
            f"Added sub-topic '{clean_subtopic}' to Week {plan.week_number}: {plan.main_topic}."
        )
    else:
        await update.effective_message.reply_text(
            f"'{clean_subtopic}' is already a sub-topic for Week {plan.week_number}: {plan.main_topic}."
        )


async def subtopic_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        today = dt.datetime.now(ZoneInfo(user.settings.timezone)).date()
        try:
            plan = list_current_subtopics(session, user=user, today=today)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return
        text = format_current_subtopics(plan)
        session.commit()
    await update.effective_message.reply_text(text)


async def subtopic_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        today = dt.datetime.now(ZoneInfo(user.settings.timezone)).date()
        try:
            plan, count = clear_current_subtopics(session, user=user, today=today)
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return
        session.commit()
    word = "sub-topic" if count == 1 else "sub-topics"
    await update.effective_message.reply_text(
        f"Cleared {count} {word} from Week {plan.week_number}: {plan.main_topic}."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        plan_count, setting_count = reset_user_study_plan(session, user=user)
        session.commit()
    await update.effective_message.reply_text(
        f"Reset study_plan. Removed {plan_count} study-plan weeks and "
        f"{setting_count} topic learning settings.\n"
        "Use /learning-setting <topic> <weeks> to build a new future plan."
    )


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        today = dt.datetime.now(ZoneInfo(user.settings.timezone)).date()
        try:
            current, removed_count, next_plan = skip_current_topic_remainder(
                session,
                user=user,
                today=today,
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return
        session.commit()
    if removed_count == 0:
        await update.effective_message.reply_text(
            f"No future {current.main_topic} weeks were found to skip. "
            "Your next study-plan stage is already next."
        )
        return
    if next_plan:
        await update.effective_message.reply_text(
            f"Skipped {removed_count} future {current.main_topic} week(s). "
            f"Next week is now Week {next_plan.week_number}: {next_plan.main_topic}."
        )
    else:
        await update.effective_message.reply_text(
            f"Skipped {removed_count} future {current.main_topic} week(s). "
            "No future topic remains; use /learning-setting to extend the study_plan."
        )


async def nextweek(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cfa_vocab_bot.services.content_engine import next_plan

    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        plan = next_plan(session, user)
        text = (
            f"Next week: Week {plan.week_number} - {plan.main_topic}\n"
            f"Focus: {', '.join(plan.subtopics) if plan.subtopics else plan.reading_or_module_name or 'n/a'}"
            if plan
            else "No upcoming topic found."
        )
        await update.effective_message.reply_text(text)


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        user.paused = True
        session.commit()
        _sync_scheduled_jobs(context, user)
    await update.effective_message.reply_text("Scheduled messages are paused. Use /resume to turn them back on.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        user.paused = False
        session.commit()
        _sync_scheduled_jobs(context, user)
    await update.effective_message.reply_text("Scheduled messages are active again.")


def _parse_setting_value(raw: str):
    if ":" in raw and len(raw) <= 5:
        hour, minute = raw.split(":", 1)
        return dt.time(int(hour), int(minute))
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        pass
    try:
        return int(raw)
    except ValueError:
        return raw


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        if len(args) >= 2:
            field = args[0]
            raw_value = " ".join(args[1:])
            allowed = {
                "timezone",
                "daily_vocab_count",
                "exam_date",
                "daily_send_time",
                "mini_review_time",
                "weekly_quiz_time",
                "weekly_recap_time",
                "quiet_hours_start",
                "quiet_hours_end",
            }
            if field not in allowed:
                await update.effective_message.reply_text(f"Unknown setting '{field}'.")
                return
            if field == "timezone":
                try:
                    ZoneInfo(raw_value)
                except ZoneInfoNotFoundError:
                    await update.effective_message.reply_text(f"Unknown timezone: {raw_value}")
                    return
                value = raw_value
            else:
                value = _parse_setting_value(raw_value)
            setattr(user.settings, field, value)
            session.commit()
            _sync_scheduled_jobs(context, user)
            await update.effective_message.reply_text(f"Updated {field} to {raw_value}.")
            return
        text = (
            "Settings\n"
            f"timezone: {user.settings.timezone}\n"
            f"daily_vocab_count: {user.settings.daily_vocab_count}\n"
            f"daily_send_time: {user.settings.daily_send_time.strftime('%H:%M')}\n"
            f"mini_review_time: {user.settings.mini_review_time.strftime('%H:%M')}\n"
            f"weekly_quiz_time: {user.settings.weekly_quiz_time.strftime('%H:%M')}\n"
            f"exam_date: {user.settings.exam_date or 'not set'}\n\n"
            "Update with /settings timezone America/Chicago or /settings daily_send_time 07:30."
        )
        await update.effective_message.reply_text(text)


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    fmt = (context.args[0].lower() if context.args else "csv")
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        content = export_anki_tsv(session, user) if fmt == "anki" else export_vocab_csv(session, user)
    suffix = "tsv" if fmt == "anki" else "csv"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=f".{suffix}", delete=False) as file:
        file.write(content)
        temp_path = Path(file.name)
    await update.effective_message.reply_document(temp_path.open("rb"), filename=f"cfa_vocab.{suffix}")
    temp_path.unlink(missing_ok=True)


def _parse_research_args(args: list[str]) -> tuple[str, str | None, int]:
    if len(args) < 2:
        raise ValueError(
            "Use /research <topic> <number>, for example /research Fixed Income 10. "
            "For sub-topics, use /research Quantitative Methods - Hypothesis Testing 10"
        )
    try:
        number = int(args[-1])
    except ValueError as exc:
        raise ValueError("The last argument must be a number.") from exc
    if number < 1:
        raise ValueError("Number must be at least 1.")
    topic_parts = args[:-1]
    subtopic = None
    if "-" in topic_parts:
        separator_index = topic_parts.index("-")
        topic = " ".join(topic_parts[:separator_index]).strip()
        subtopic = " ".join(topic_parts[separator_index + 1 :]).strip() or None
    else:
        topic = " ".join(topic_parts).strip()
    if not topic:
        raise ValueError("Topic cannot be empty.")
    return topic, subtopic, min(number, MAX_RESEARCH_NUMBER)


async def research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        topic_text, subtopic_text, number = _parse_research_args(context.args or [])
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return

    settings = _settings(context)
    if not settings.openai_api_key:
        await update.effective_message.reply_text(
            "OPENAI_API_KEY is not configured yet. Add it to .env, restart the bot, "
            "then run /research again."
        )
        return

    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, settings)
        resolution = resolve_topic_for_learning(session, topic_text)
        if not resolution.is_valid:
            if resolution.suggestion and subtopic_text:
                text = (
                    f"Topic not found: {topic_text}\n"
                    f"Did you mean: {resolution.suggestion}?\n"
                    f"Run /research {resolution.suggestion} - {subtopic_text} {number} to confirm."
                )
            else:
                text = format_topic_validation_error(
                    topic=topic_text,
                    weeks=number,
                    suggestion=resolution.suggestion,
                    available_topics=resolution.available_topics,
                ).replace("/learning-setting", "/research")
            await update.effective_message.reply_text(text)
            return
        topic_text = resolution.topic or topic_text
        focus_text = f"{topic_text} - {subtopic_text}" if subtopic_text else topic_text
        status_message = await update.effective_message.reply_text(
            f"Researching CFA Level I terms for '{focus_text}'..."
        )
        try:
            suggestions = await research_topic(
                session,
                user=user,
                topic=topic_text,
                subtopic=subtopic_text,
                number=number,
                provider=provider_from_settings(settings),
                model_name=settings.openai_research_model,
            )
            session.commit()
        except ResearchUnavailable as exc:
            session.rollback()
            await status_message.edit_text(f"Research failed: {exc}")
            return
    await status_message.edit_text(
        format_research_suggestions(suggestions),
        reply_markup=research_keyboard(suggestions) if suggestions else None,
        disable_web_page_preview=True,
    )


async def export_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        content = export_all_user_data(session, user)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as file:
        file.write(content)
        temp_path = Path(file.name)
    await update.effective_message.reply_document(temp_path.open("rb"), filename="cfa_vocab_my_data.json")
    temp_path.unlink(missing_ok=True)


async def delete_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with _session_factory(context)() as session:
        user = get_user_by_chat_id(session, _chat_id(update))
        if user:
            user_id = user.id
            delete_user_data(session, user)
            session.commit()
            _remove_scheduled_jobs(context, user_id)
    await update.effective_message.reply_text("Your CFA Vocab Bot data has been deleted.")


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    terms = [arg.strip() for arg in context.args if arg.strip()]
    if not terms:
        await update.effective_message.reply_text("Use /error duration convexity callable bond")
        return
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        matched = []
        for term in terms:
            vocab = session.scalar(select(VocabItem).where(VocabItem.term.ilike(term)))
            if vocab:
                state = get_or_create_review_state(session, user.id, vocab.id)
                apply_review_result(state, False, reviewed_at=utc_now(), reason="personal_error_log")
                matched.append(vocab.term)
        session.commit()
    await update.effective_message.reply_text(
        "Added to weak list: " + (", ".join(matched) if matched else "no known seed terms matched")
    )


async def handle_timeline_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.effective_message.document
    if document is None:
        return
    suffix = Path(document.file_name or "").suffix.lower()
    if suffix not in {".csv", ".json"}:
        await update.effective_message.reply_text("Please upload a CSV or JSON timeline.")
        return
    telegram_file = await document.get_file()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
        temp_path = Path(temp.name)
    await telegram_file.download_to_drive(custom_path=temp_path)
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        count, warnings = import_timeline(session, user_id=user.id, path=temp_path)
        session.commit()
    temp_path.unlink(missing_ok=True)
    warning_text = "\n".join(warnings[:5])
    await update.effective_message.reply_text(
        f"Imported {count} timeline rows."
        + (f"\nWarnings:\n{warning_text}" if warning_text else "")
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    with _session_factory(context)() as session:
        user = _ensure_user_from_update(session, update, _settings(context))
        if data.startswith(("know:", "easy:", "hard:", "review:", "example:", "quizme:")):
            action, raw_vocab_id = data.split(":", 1)
            vocab = session.get(VocabItem, int(raw_vocab_id))
            if not vocab:
                await query.edit_message_text("That vocab item no longer exists.")
                return
            state = get_or_create_review_state(session, user.id, vocab.id)
            if action in {"know", "easy"}:
                apply_review_result(state, True, reason=action)
                response = f"Marked '{vocab.term}' as easier. Next review: {state.next_review_at}."
            elif action in {"hard", "review"}:
                apply_review_result(state, False, reason=action)
                response = f"Marked '{vocab.term}' for review. It will come back soon."
            elif action == "example":
                response = f"{vocab.term}\nExample: {vocab.example}\nTrap: {vocab.exam_trap or 'n/a'}"
            else:
                quiz_result = active_quiz(session, user) or create_weekly_quiz(session, user)
                question = next_unanswered_question(session, user, quiz_result)
                session.commit()
                if question:
                    await query.message.reply_text(
                        format_quiz_question(question, quiz_result),
                        reply_markup=quiz_keyboard(quiz_result.id, question),
                    )
                    return
                response = "No quiz question is available right now."
            session.commit()
            await query.message.reply_text(response)
            return

        if data.startswith("quiz:"):
            _, raw_quiz_id, raw_question_id, choice = data.split(":", 3)
            quiz_result = session.get(QuizResult, int(raw_quiz_id))
            question = session.get(QuizQuestion, int(raw_question_id))
            if quiz_result is None or question is None:
                await query.message.reply_text("This quiz is no longer available.")
                return
            attempt = grade_answer(
                session,
                user=user,
                quiz=quiz_result,
                question=question,
                selected_answer=choice,
            )
            next_question = next_unanswered_question(session, user, quiz_result)
            session.commit()
            prefix = "Correct." if attempt.is_correct else f"Not quite. Correct answer: {question.correct_answer}."
            await query.message.reply_text(f"{prefix}\n{question.explanation}")
            if next_question:
                await query.message.reply_text(
                    format_quiz_question(next_question, quiz_result),
                    reply_markup=quiz_keyboard(quiz_result.id, next_question),
                )
            else:
                await query.message.reply_text(quiz_feedback(session, quiz_result))
            return

        if data.startswith("rs:"):
            _, raw_suggestion_id, action = data.split(":", 2)
            try:
                if action == "approve":
                    suggestion, vocab, status = approve_research_suggestion(
                        session, user=user, suggestion_id=int(raw_suggestion_id)
                    )
                    session.commit()
                    if status == "approved" and vocab:
                        await query.message.reply_text(
                            f"Added '{vocab.term}' to the learning database."
                        )
                    elif status == "duplicate" and vocab:
                        await query.message.reply_text(
                            f"'{suggestion.term}' is already covered by '{vocab.term}'."
                        )
                    else:
                        await query.message.reply_text(
                            f"Suggestion '{suggestion.term}' status: {status}."
                        )
                elif action == "reject":
                    suggestion = reject_research_suggestion(
                        session, user=user, suggestion_id=int(raw_suggestion_id)
                    )
                    session.commit()
                    await query.message.reply_text(f"Rejected '{suggestion.term}'.")
            except ValueError as exc:
                session.rollback()
                await query.message.reply_text(str(exc))


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("review", review))
    application.add_handler(CommandHandler("quiz", quiz))
    application.add_handler(CommandHandler("progress", progress))
    application.add_handler(CommandHandler("weak", weak))
    application.add_handler(CommandHandler("topic", topic))
    application.add_handler(CommandHandler("topics_display", topics_display))
    application.add_handler(
        MessageHandler(filters.Regex(r"^/topics-display(@\w+)?(?:\s|$)"), topics_display)
    )
    application.add_handler(CommandHandler("learning_setting", learning_setting))
    application.add_handler(
        MessageHandler(filters.Regex(r"^/learning-setting(@\w+)?(?:\s|$)"), learning_setting)
    )
    application.add_handler(CommandHandler("subtopic_add", subtopic_add))
    application.add_handler(
        MessageHandler(filters.Regex(r"^/subtopic-add(@\w+)?(?:\s|$)"), subtopic_add)
    )
    application.add_handler(CommandHandler("subtopic_list", subtopic_list))
    application.add_handler(
        MessageHandler(filters.Regex(r"^/subtopic-list(@\w+)?(?:\s|$)"), subtopic_list)
    )
    application.add_handler(CommandHandler("subtopic_clear", subtopic_clear))
    application.add_handler(
        MessageHandler(filters.Regex(r"^/subtopic-clear(@\w+)?(?:\s|$)"), subtopic_clear)
    )
    application.add_handler(CommandHandler("nextweek", nextweek))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("skip", skip))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("export", export))
    application.add_handler(CommandHandler("research", research))
    application.add_handler(CommandHandler("export_my_data", export_my_data))
    application.add_handler(CommandHandler("delete_my_data", delete_my_data))
    application.add_handler(CommandHandler("error", error))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_timeline_upload))
    application.add_handler(CallbackQueryHandler(handle_callback))
