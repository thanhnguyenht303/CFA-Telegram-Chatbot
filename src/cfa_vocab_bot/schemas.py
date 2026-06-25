from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class TimelineRow(BaseModel):
    week_number: int
    start_date: dt.date
    end_date: dt.date
    main_topic: str
    subtopics: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    curriculum_year: int | None = None
    exam_window: str | None = None
    exam_date: dt.date | None = None
    official_topic_weight: float | None = None
    los_ids: list[str] = Field(default_factory=list)
    reading_or_module_name: str | None = None
    exam_phase: str = "learning"


class VocabCard(BaseModel):
    id: int
    term: str
    topic: str
    subtopic: str | None = None
    english_definition: str
    vietnamese_translation: str
    example: str
    exam_trap: str | None = None
    tags: list[str] = Field(default_factory=list)


class ProgressSnapshot(BaseModel):
    total_terms_seen: int
    mastered: int
    reviewing: int
    weak: int
    weekly_quiz_score: float | None = None
    current_topic: str | None = None
    next_topic: str | None = None
    streak_days: int
    review_debt: int
    weighted_readiness: dict[str, float] = Field(default_factory=dict)


class ResearchSource(BaseModel):
    source_name: str
    source_type: str = "public_web"
    source_reference: str | None = None
    url: str | None = None


class ResearchCandidate(BaseModel):
    term: str
    aliases: list[str] = Field(default_factory=list)
    topic: str
    subtopic: str | None = None
    english_definition: str
    vietnamese_translation: str
    example: str
    exam_trap: str | None = None
    tags: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    priority_score: float = 0.0
    sources: list[ResearchSource] = Field(default_factory=list)
    research_reason: str | None = None

