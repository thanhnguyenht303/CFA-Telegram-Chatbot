from __future__ import annotations

import logging
from logging.config import dictConfig

from .config import Settings


class SecretMaskFilter(logging.Filter):
    """Prevent common secret values from being emitted in application logs."""

    def __init__(self, secrets: list[str | None]) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            if secret and secret in message:
                record.msg = message.replace(secret, "[REDACTED]")
                record.args = ()
        return True


def configure_logging(settings: Settings) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["secrets"],
                }
            },
            "filters": {
                "secrets": {
                    "()": SecretMaskFilter,
                    "secrets": [
                        settings.telegram_bot_token,
                        settings.openai_api_key,
                        settings.webhook_secret,
                        settings.admin_api_key,
                    ],
                }
            },
            "root": {"handlers": ["console"], "level": settings.log_level.upper()},
        }
    )

