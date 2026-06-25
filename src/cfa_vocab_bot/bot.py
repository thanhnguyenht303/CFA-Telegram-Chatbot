from __future__ import annotations

import logging

from telegram.ext import Application

from cfa_vocab_bot.config import Settings
from cfa_vocab_bot.db import create_db_engine, create_session_factory
from cfa_vocab_bot.models import Base
from cfa_vocab_bot.scheduler import build_scheduler
from cfa_vocab_bot.telegram.handlers import COMMANDS, register_handlers

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(COMMANDS)
    scheduler = build_scheduler(application.bot_data["session_factory"], application.bot)
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info("Registered Telegram commands and started scheduler with %s jobs.", len(scheduler.get_jobs()))


async def _post_shutdown(application: Application) -> None:
    scheduler = application.bot_data.get("scheduler")
    if scheduler:
        scheduler.shutdown(wait=False)


def create_application(settings: Settings) -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot.")
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["session_factory"] = session_factory
    register_handlers(app)
    return app


def run_bot(settings: Settings) -> None:
    app = create_application(settings)
    if settings.polling:
        app.run_polling(allowed_updates=None)
    else:
        if not settings.webhook_url:
            raise RuntimeError("WEBHOOK_URL is required when POLLING=false.")
        app.run_webhook(
            listen="0.0.0.0",
            port=8080,
            webhook_url=settings.webhook_url,
            secret_token=settings.webhook_secret,
        )

