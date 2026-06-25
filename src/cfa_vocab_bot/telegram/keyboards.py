from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from cfa_vocab_bot.models import QuizQuestion, ResearchSuggestion, VocabItem


def vocab_keyboard(vocab_items: Sequence[VocabItem]) -> InlineKeyboardMarkup:
    rows = []
    for vocab in vocab_items[:5]:
        rows.append(
            [
                InlineKeyboardButton("I know this", callback_data=f"know:{vocab.id}"),
                InlineKeyboardButton("Review later", callback_data=f"review:{vocab.id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton("Give example", callback_data=f"example:{vocab.id}"),
                InlineKeyboardButton("Too hard", callback_data=f"hard:{vocab.id}"),
                InlineKeyboardButton("Too easy", callback_data=f"easy:{vocab.id}"),
            ]
        )
    if vocab_items:
        rows.append([InlineKeyboardButton("Quiz me", callback_data=f"quizme:{vocab_items[0].id}")])
    return InlineKeyboardMarkup(rows)


def quiz_keyboard(quiz_id: int, question: QuizQuestion) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("A", callback_data=f"quiz:{quiz_id}:{question.id}:A"),
                InlineKeyboardButton("B", callback_data=f"quiz:{quiz_id}:{question.id}:B"),
                InlineKeyboardButton("C", callback_data=f"quiz:{quiz_id}:{question.id}:C"),
            ]
        ]
    )


def research_keyboard(suggestions: Sequence[ResearchSuggestion]) -> InlineKeyboardMarkup:
    rows = []
    for suggestion in suggestions:
        rows.append(
            [
                InlineKeyboardButton(
                    f"Approve {suggestion.term[:24]}",
                    callback_data=f"rs:{suggestion.id}:approve",
                ),
                InlineKeyboardButton("Reject", callback_data=f"rs:{suggestion.id}:reject"),
            ]
        )
    return InlineKeyboardMarkup(rows)
