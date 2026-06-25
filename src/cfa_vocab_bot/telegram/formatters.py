from __future__ import annotations

from collections.abc import Sequence

from cfa_vocab_bot.models import QuizQuestion, QuizResult, ResearchSuggestion, StudyPlan, VocabItem
from cfa_vocab_bot.schemas import ProgressSnapshot


def format_vocab_card(index: int, vocab: VocabItem) -> str:
    trap = f"\nExam trap: {vocab.exam_trap}" if vocab.exam_trap else ""
    return (
        f"{index}. {vocab.term}\n"
        f"Meaning: {vocab.english_definition}\n"
        f"Vietnamese: {vocab.vietnamese_translation}\n"
        f"Example: {vocab.example}"
        f"{trap}\n"
        f"Tag: {vocab.topic}"
    )


def format_daily_vocab(plan: StudyPlan | None, vocab_items: Sequence[VocabItem]) -> str:
    title = "CFA Vocab"
    if plan:
        title = f"CFA Vocab - Week {plan.week_number}, Day topic"
    topic = plan.main_topic if plan else (vocab_items[0].topic if vocab_items else "General")
    goal = plan.reading_or_module_name if plan and plan.reading_or_module_name else topic
    cards = "\n\n".join(format_vocab_card(i, vocab) for i, vocab in enumerate(vocab_items, 1))
    return (
        f"{title}\n"
        f"Topic: {topic}\n"
        f"Goal today: {goal}\n\n"
        f"{cards}\n\n"
        "Tonight, when you study CFA, try to notice how these terms appear in question stems."
    )


def format_mini_review(vocab_items: Sequence[VocabItem]) -> str:
    lines = ["Mini review - quick recall"]
    for index, vocab in enumerate(vocab_items, 1):
        lines.append(f"{index}. What does '{vocab.term}' mean in CFA context?")
    return "\n".join(lines)


def format_quiz_question(question: QuizQuestion, quiz: QuizResult) -> str:
    return (
        f"Weekly CFA Vocab Quiz - {quiz.topic or 'CFA Level I'}\n"
        f"Question {question.order_index + 1}/{quiz.total_questions}\n\n"
        f"{question.question_text}\n\n"
        f"A. {question.option_a}\n"
        f"B. {question.option_b}\n"
        f"C. {question.option_c}"
    )


def format_weekly_recap(
    snapshot: ProgressSnapshot,
    weak_rows: Sequence[tuple[VocabItem, object]],
) -> str:
    weak_terms = "\n".join(
        f"- {vocab.term}: wrong answers or due reviews" for vocab, _state in weak_rows
    )
    weak_block = weak_terms or "No weak terms yet."
    return (
        "Weekly CFA Vocab Recap\n"
        f"Total terms learned: {snapshot.total_terms_seen}\n"
        f"Mastered: {snapshot.mastered}\n"
        f"Reviewing: {snapshot.reviewing}\n"
        f"Weak: {snapshot.weak}\n"
        f"Quiz score: {snapshot.weekly_quiz_score if snapshot.weekly_quiz_score is not None else 'n/a'}\n"
        f"Current topic: {snapshot.current_topic or 'not set'}\n"
        f"Next topic: {snapshot.next_topic or 'not set'}\n\n"
        f"Top weak terms:\n{weak_block}"
    )


def format_research_suggestions(suggestions: Sequence[ResearchSuggestion]) -> str:
    if not suggestions:
        return "No new research suggestions were found after duplicate filtering."
    lines = ["Research suggestions", "Approve only the terms you want added to the learning database."]
    for index, suggestion in enumerate(suggestions, 1):
        source_names = ", ".join(
            source.get("source_name", "source") for source in suggestion.sources[:2]
        )
        source_note = f"\nSources: {source_names}" if source_names else ""
        trap_note = f"\nExam trap: {suggestion.exam_trap}" if suggestion.exam_trap else ""
        lines.append(
            f"{index}. [{suggestion.id}] {suggestion.term}\n"
            f"Meaning: {suggestion.english_definition[:220]}\n"
            f"Vietnamese: {suggestion.vietnamese_translation[:180]}"
            f"{trap_note}"
            f"{source_note}"
        )
    return "\n\n".join(lines)


def format_available_topics(topic_counts: Sequence[tuple[str, int]]) -> str:
    if not topic_counts:
        return "No active approved vocab topics are available yet."
    lines = ["Available vocab topics"]
    for topic, count in topic_counts:
        word = "word" if count == 1 else "words"
        lines.append(f"- {topic}: {count} {word}")
    return "\n".join(lines)
