from __future__ import annotations

from cfa_vocab_bot.models import VocabItem
from cfa_vocab_bot.services.topics import available_topic_counts
from cfa_vocab_bot.telegram.formatters import format_available_topics


def test_available_topic_counts_show_only_active_approved_topics(session, seeded):
    hidden = VocabItem(
        term="Hidden term",
        normalized_term="hidden term",
        topic="Hidden Topic",
        subtopic="hidden",
        english_definition="This should not appear.",
        vietnamese_translation="Khong hien thi.",
        example="This term is not approved.",
        exam_trap="Not relevant.",
        qa_status="needs_review",
        status="active",
    )
    inactive = VocabItem(
        term="Inactive term",
        normalized_term="inactive term",
        topic="Inactive Topic",
        subtopic="inactive",
        english_definition="This should not appear either.",
        vietnamese_translation="Khong hien thi.",
        example="This term is inactive.",
        exam_trap="Not relevant.",
        qa_status="approved",
        status="inactive",
    )
    session.add_all([hidden, inactive])
    session.commit()

    counts = dict(available_topic_counts(session))

    assert counts["Financial Statement Analysis"] == 25
    assert counts["Fixed Income"] == 8
    assert "Hidden Topic" not in counts
    assert "Inactive Topic" not in counts


def test_format_available_topics_includes_counts():
    message = format_available_topics([("Ethics", 3), ("Fixed Income", 1)])

    assert "Available vocab topics" in message
    assert "- Ethics: 3 words" in message
    assert "- Fixed Income: 1 word" in message

