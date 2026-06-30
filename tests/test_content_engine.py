from __future__ import annotations

import datetime as dt

from cfa_vocab_bot.models import VocabItem
from cfa_vocab_bot.services.content_engine import record_vocab_delivery, select_daily_vocab
from cfa_vocab_bot.services.importers import import_timeline


def test_daily_selection_excludes_previously_sent_terms(session, user, seeded, current_week_csv):
    import_timeline(session, user_id=user.id, path=current_week_csv)
    session.commit()
    plan, day_one = select_daily_vocab(session, user, today=dt.date(2026, 6, 24), count=5)
    assert len(day_one) == 5
    record_vocab_delivery(session, user=user, vocab_items=day_one, delivery_type="daily_vocab", plan=plan)
    session.commit()
    _plan, day_two = select_daily_vocab(session, user, today=dt.date(2026, 6, 25), count=5)
    assert len(day_two) == 5
    assert {item.normalized_term for item in day_one}.isdisjoint(
        {item.normalized_term for item in day_two}
    )


def test_needs_review_vocab_is_not_selected(session, user, seeded, current_week_csv):
    import_timeline(session, user_id=user.id, path=current_week_csv)
    item = session.query(VocabItem).first()
    item.qa_status = "needs_review"
    session.commit()
    _plan, vocab = select_daily_vocab(session, user, today=dt.date(2026, 6, 24), count=25)
    assert item not in vocab


def test_daily_selection_prefers_current_plan_subtopics(session, user, seeded, current_week_csv):
    import_timeline(session, user_id=user.id, path=current_week_csv)
    session.commit()

    _plan, vocab = select_daily_vocab(session, user, today=dt.date(2026, 6, 24), count=4)

    assert [item.term for item in vocab] == [
        "Operating cash flow",
        "Ratio analysis",
        "Gross profit margin",
        "Capital expenditure",
    ]
