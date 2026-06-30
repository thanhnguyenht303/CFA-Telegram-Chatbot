from __future__ import annotations

from cfa_vocab_bot.models import VocabItem
from cfa_vocab_bot.services.topics import available_topic_counts, resolve_topic_for_learning
from cfa_vocab_bot.telegram.formatters import format_available_topics, format_topic_validation_error


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


def test_resolve_topic_for_learning_canonicalizes_known_topic(session, seeded):
    resolution = resolve_topic_for_learning(session, " fixed   income ")

    assert resolution.is_valid
    assert resolution.topic == "Fixed Income"
    assert resolution.suggestion is None


def test_resolve_topic_for_learning_suggests_typo_without_accepting_it(session, seeded):
    resolution = resolve_topic_for_learning(session, "Quantiative Method")

    assert not resolution.is_valid
    assert resolution.topic is None
    assert resolution.suggestion == "Quantitative Methods"


def test_resolve_topic_for_learning_rejects_unknown_topic_without_suggestion(session, seeded):
    resolution = resolve_topic_for_learning(session, "Astrology")

    assert not resolution.is_valid
    assert resolution.topic is None
    assert resolution.suggestion is None


def test_format_topic_validation_error_shows_confirmation_command():
    message = format_topic_validation_error(
        topic="Quantiative Method",
        weeks=2,
        suggestion="Quantitative Methods",
        available_topics=[],
    )

    assert "Topic not found: Quantiative Method" in message
    assert "Did you mean: Quantitative Methods?" in message
    assert "/learning-setting Quantitative Methods 2" in message
