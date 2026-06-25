from __future__ import annotations

from cfa_vocab_bot.models import ResearchSuggestion, VocabItem
from cfa_vocab_bot.schemas import ResearchCandidate, ResearchSource
from cfa_vocab_bot.services.research import (
    approve_research_suggestion,
    existing_topic_terms_and_aliases,
    research_topic,
    store_research_candidates,
)
from cfa_vocab_bot.telegram.formatters import format_research_suggestions


def _candidate(term: str, topic: str = "Portfolio Management") -> ResearchCandidate:
    return ResearchCandidate(
        term=term,
        aliases=[],
        topic=topic,
        subtopic="portfolio risk",
        english_definition=f"A CFA Level I definition for {term}.",
        vietnamese_translation=f"Nghia cua {term}.",
        example=f"An analyst uses {term} when evaluating a CFA-style case.",
        exam_trap=f"Do not confuse {term} with a nearby concept.",
        tags=[topic, "research"],
        difficulty="medium",
        priority_score=88,
        sources=[
            ResearchSource(
                source_name="Public CFA-related source",
                source_type="public_web",
                source_reference="Research summary",
                url="https://example.com",
            )
        ],
        research_reason="Useful for CFA Level I reading comprehension.",
    )


def test_store_research_candidates_filters_existing_duplicates(session, user, seeded):
    suggestions = store_research_candidates(
        session,
        user=user,
        topic="Financial Statement Analysis",
        requested_number=3,
        candidates=[
            _candidate("Revenue recognition", "Financial Statement Analysis"),
            _candidate("Tracking error", "Portfolio Management"),
        ],
        model_name="test-model",
    )
    session.commit()

    assert len(suggestions) == 1
    assert suggestions[0].term == "Tracking error"
    assert session.query(ResearchSuggestion).count() == 1


async def test_research_topic_retries_until_requested_count_after_duplicate_filtering(
    session, user, seeded
):
    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def research(self, *, topic, number, exclude_terms=()):
            self.calls.append({"topic": topic, "number": number, "exclude_terms": list(exclude_terms)})
            if len(self.calls) == 1:
                return [
                    _candidate("Revenue recognition", "Financial Statement Analysis"),
                    _candidate("Operating cash flow", "Financial Statement Analysis"),
                    _candidate("New FSA research term one", "Financial Statement Analysis"),
                ]
            return [
                _candidate("New FSA research term two", "Financial Statement Analysis"),
                _candidate("New FSA research term three", "Financial Statement Analysis"),
            ]

    provider = FakeProvider()

    suggestions = await research_topic(
        session,
        user=user,
        topic="Financial Statement Analysis",
        number=3,
        provider=provider,
        model_name="fake-model",
    )
    session.commit()

    assert len(suggestions) == 3
    assert [suggestion.term for suggestion in suggestions] == [
        "New FSA research term one",
        "New FSA research term two",
        "New FSA research term three",
    ]
    assert len(provider.calls) == 2
    assert "Revenue recognition" in provider.calls[0]["exclude_terms"]
    assert "OCF" in provider.calls[0]["exclude_terms"]


def test_existing_topic_terms_and_aliases_includes_aliases(session, seeded):
    terms = existing_topic_terms_and_aliases(session, "Financial Statement Analysis")

    assert "Revenue recognition" in terms
    assert "OCF" in terms


def test_approve_research_suggestion_creates_active_vocab(session, user):
    suggestions = store_research_candidates(
        session,
        user=user,
        topic="Portfolio Management",
        requested_number=1,
        candidates=[_candidate("Tracking error")],
        model_name="test-model",
    )
    suggestion_id = suggestions[0].id

    suggestion, vocab, status = approve_research_suggestion(
        session, user=user, suggestion_id=suggestion_id
    )
    session.commit()

    assert status == "approved"
    assert suggestion.status == "approved"
    assert vocab is not None
    assert vocab.qa_status == "approved"
    assert vocab.status == "active"
    assert session.query(VocabItem).filter_by(term="Tracking error").one()


def test_format_research_suggestions_includes_vietnamese_meaning(session, user):
    suggestions = store_research_candidates(
        session,
        user=user,
        topic="Portfolio Management",
        requested_number=1,
        candidates=[_candidate("Tracking error")],
        model_name="test-model",
    )
    session.commit()

    message = format_research_suggestions(suggestions)

    assert "Tracking error" in message
    assert "Meaning:" in message
    assert "Vietnamese: Nghia cua Tracking error." in message
    assert "Exam trap:" in message
