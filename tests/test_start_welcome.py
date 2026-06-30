from __future__ import annotations

import datetime as dt

from cfa_vocab_bot.models import User, UserSettings
from cfa_vocab_bot.telegram.formatters import format_start_welcome


def test_start_welcome_uses_user_settings_not_fixed_defaults():
    user = User(chat_id=123, telegram_user_id=456)
    user.settings = UserSettings(
        timezone="Asia/Bangkok",
        daily_vocab_count=7,
        daily_send_time=dt.time(6, 45),
        mini_review_time=dt.time(22, 5),
        weekly_quiz_day=2,
        weekly_quiz_time=dt.time(8, 15),
        weekly_recap_day=4,
        weekly_recap_time=dt.time(19, 20),
    )

    message = format_start_welcome(user)

    assert "Timezone: Asia/Bangkok" in message
    assert "Daily vocab: 7 terms at 06:45" in message
    assert "Mini review: 22:05" in message
    assert "Weekly quiz: Wednesday 08:15" in message
    assert "Weekly recap: Friday 19:20" in message
    assert "Saturday 09:00 quiz, Sunday 18:30 recap" not in message

