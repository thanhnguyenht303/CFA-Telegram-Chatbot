from __future__ import annotations

from cfa_vocab_bot.services.content_engine import record_vocab_delivery, select_daily_vocab
from cfa_vocab_bot.services.export import export_anki_tsv, export_vocab_csv
from cfa_vocab_bot.services.importers import import_timeline, plan_for_date


def test_import_timeline_and_export(session, user, seeded, current_week_csv):
    count, warnings = import_timeline(session, user_id=user.id, path=current_week_csv)
    assert count == 1
    assert warnings == []
    plan = plan_for_date(session, user.id, __import__("datetime").date(2026, 6, 24))
    assert plan is not None
    assert plan.main_topic == "Financial Statement Analysis"

    plan, vocab = select_daily_vocab(session, user, today=plan.start_date, count=5)
    record_vocab_delivery(session, user=user, vocab_items=vocab, delivery_type="daily_vocab", plan=plan)
    session.commit()
    csv_data = export_vocab_csv(session, user)
    anki = export_anki_tsv(session, user)
    assert "Operating cash flow" in csv_data
    assert "\t" in anki
