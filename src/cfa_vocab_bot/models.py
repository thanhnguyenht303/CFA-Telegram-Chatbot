from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    settings: Mapped["UserSettings"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    study_plan: Mapped[list["StudyPlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    review_states: Mapped[list["ReviewState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    topic_learning_settings: Mapped[list["TopicLearningSetting"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    language_mode: Mapped[str] = mapped_column(String(32), default="en_vi", nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="America/Chicago", nullable=False)
    daily_vocab_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    review_intensity: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    daily_send_time: Mapped[dt.time] = mapped_column(Time, default=dt.time(7, 30), nullable=False)
    mini_review_time: Mapped[dt.time] = mapped_column(Time, default=dt.time(21, 40), nullable=False)
    weekly_quiz_day: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    weekly_quiz_time: Mapped[dt.time] = mapped_column(Time, default=dt.time(9, 0), nullable=False)
    weekly_recap_day: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    weekly_recap_time: Mapped[dt.time] = mapped_column(Time, default=dt.time(18, 30), nullable=False)
    exam_date: Mapped[dt.date | None] = mapped_column(Date)
    quiet_hours_start: Mapped[dt.time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[dt.time | None] = mapped_column(Time)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="settings")


class TopicLearningSetting(Base):
    __tablename__ = "topic_learning_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_topic", name="uq_topic_learning_user_topic"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_topic: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="topic_learning_settings")


class StudyPlan(Base):
    __tablename__ = "study_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_number: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, index=True, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, index=True, nullable=False)
    main_topic: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    subtopics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    learning_objectives: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    curriculum_year: Mapped[int | None] = mapped_column(Integer)
    exam_window: Mapped[str | None] = mapped_column(String(120))
    exam_date: Mapped[dt.date | None] = mapped_column(Date)
    official_topic_weight: Mapped[float | None] = mapped_column(Float)
    los_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reading_or_module_name: Mapped[str | None] = mapped_column(String(255))
    exam_phase: Mapped[str] = mapped_column(String(40), default="learning", nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User | None] = relationship(back_populates="study_plan")


class VocabItem(Base):
    __tablename__ = "vocab_items"
    __table_args__ = (
        UniqueConstraint(
            "normalized_term", "topic", "subtopic", name="uq_vocab_normalized_topic_subtopic"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    subtopic: Mapped[str | None] = mapped_column(String(255), index=True)
    pronunciation: Mapped[str | None] = mapped_column(String(255))
    english_definition: Mapped[str] = mapped_column(Text, nullable=False)
    vietnamese_translation: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str] = mapped_column(Text, nullable=False)
    exam_trap: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    item_type: Mapped[str] = mapped_column(String(40), default="vocab", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    qa_status: Mapped[str] = mapped_column(String(40), default="auto_approved", index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    curriculum_year: Mapped[int | None] = mapped_column(Integer)
    los_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    official_topic_weight: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default="active", index=True, nullable=False)
    source_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    aliases: Mapped[list["VocabAlias"]] = relationship(
        back_populates="vocab", cascade="all, delete-orphan"
    )
    sources: Mapped[list["VocabSource"]] = relationship(
        back_populates="vocab", cascade="all, delete-orphan"
    )


class VocabAlias(Base):
    __tablename__ = "vocab_aliases"
    __table_args__ = (UniqueConstraint("normalized_alias", name="uq_vocab_alias_normalized"),)

    id: Mapped[int] = mapped_column("alias_id", Integer, primary_key=True)
    vocab_id: Mapped[int] = mapped_column(ForeignKey("vocab_items.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(40), default="variant", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    vocab: Mapped[VocabItem] = relationship(back_populates="aliases")


class VocabSource(Base):
    __tablename__ = "vocab_sources"

    id: Mapped[int] = mapped_column("source_id", Integer, primary_key=True)
    vocab_id: Mapped[int] = mapped_column(ForeignKey("vocab_items.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    curriculum_year: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    copyright_status: Mapped[str] = mapped_column(String(80), default="public_or_rewritten")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    vocab: Mapped[VocabItem] = relationship(back_populates="sources")


class DeliveryLog(Base):
    __tablename__ = "delivery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vocab_id: Mapped[int | None] = mapped_column(ForeignKey("vocab_items.id", ondelete="SET NULL"))
    study_plan_id: Mapped[int | None] = mapped_column(ForeignKey("study_plan.id", ondelete="SET NULL"))
    delivery_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="sent", nullable=False)
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    scheduled_for: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    week_number: Mapped[int | None] = mapped_column(Integer, index=True)
    day_index: Mapped[int | None] = mapped_column(Integer)
    message_id: Mapped[int | None] = mapped_column(Integer)
    normalized_term: Mapped[str | None] = mapped_column(String(255), index=True)
    topic: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ReviewState(Base):
    __tablename__ = "review_state"
    __table_args__ = (UniqueConstraint("user_id", "vocab_id", name="uq_review_user_vocab"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vocab_id: Mapped[int] = mapped_column(ForeignKey("vocab_items.id", ondelete="CASCADE"), index=True)
    mastery_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="new", index=True, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.3, nullable=False)
    last_reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    is_weak: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    due_reason: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="review_states")
    vocab: Mapped[VocabItem] = relationship()


class QuizResult(Base):
    __tablename__ = "quiz_results"

    id: Mapped[int] = mapped_column("quiz_id", Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    study_plan_id: Mapped[int | None] = mapped_column(ForeignKey("study_plan.id", ondelete="SET NULL"))
    week_number: Mapped[int | None] = mapped_column(Integer, index=True)
    topic: Mapped[str | None] = mapped_column(String(255), index=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.order_index"
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column("question_id", Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quiz_results.quiz_id", ondelete="CASCADE"))
    vocab_id: Mapped[int] = mapped_column(ForeignKey("vocab_items.id", ondelete="CASCADE"), index=True)
    question_type: Mapped[str] = mapped_column(String(60), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str | None] = mapped_column(Text)
    option_b: Mapped[str | None] = mapped_column(Text)
    option_c: Mapped[str | None] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    quiz: Mapped[QuizResult] = relationship(back_populates="questions")
    vocab: Mapped[VocabItem] = relationship()


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (UniqueConstraint("user_id", "quiz_id", "question_id", name="uq_attempt_once"),)

    id: Mapped[int] = mapped_column("attempt_id", Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quiz_results.quiz_id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_questions.question_id", ondelete="CASCADE")
    )
    selected_answer: Mapped[str] = mapped_column(String(255), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_seconds: Mapped[int | None] = mapped_column(Integer)
    answered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentGenerationLog(Base):
    __tablename__ = "content_generation_log"

    id: Mapped[int] = mapped_column("generation_id", Integer, primary_key=True)
    vocab_id: Mapped[int | None] = mapped_column(ForeignKey("vocab_items.id", ondelete="SET NULL"))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    model_name: Mapped[str | None] = mapped_column(String(120))
    source_context: Mapped[str | None] = mapped_column(Text)
    generated_output: Mapped[str | None] = mapped_column(Text)
    qa_status: Mapped[str] = mapped_column(String(40), default="needs_review")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ResearchSuggestion(Base):
    __tablename__ = "research_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vocab_id: Mapped[int | None] = mapped_column(ForeignKey("vocab_items.id", ondelete="SET NULL"))
    topic: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    subtopic: Mapped[str | None] = mapped_column(String(255))
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    english_definition: Mapped[str] = mapped_column(Text, nullable=False)
    vietnamese_translation: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str] = mapped_column(Text, nullable=False)
    exam_trap: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    research_reason: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="suggested", index=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SchedulerJob(Base):
    __tablename__ = "scheduler_jobs"

    id: Mapped[int] = mapped_column("job_id", Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    scheduled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(40), default="scheduled", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column("event_id", Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
