from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cfa_vocab_bot.config import Settings
from cfa_vocab_bot.models import Base, User
from cfa_vocab_bot.services.seed import seed_vocab_from_json
from cfa_vocab_bot.services.users import ensure_user


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture()
def settings() -> Settings:
    return Settings(default_timezone="America/Chicago")


@pytest.fixture()
def user(session, settings) -> User:
    user = ensure_user(
        session,
        chat_id=12345,
        telegram_user_id=67890,
        username="candidate",
        first_name="CFA",
        settings=settings,
    )
    session.commit()
    return user


@pytest.fixture()
def seeded(session):
    seed_path = Path(__file__).resolve().parents[1] / "data" / "seed_vocab.json"
    count = seed_vocab_from_json(session, seed_path)
    session.commit()
    return count


@pytest.fixture()
def current_week_csv(tmp_path):
    path = tmp_path / "timeline.csv"
    path.write_text(
        "\n".join(
            [
                "week_number,start_date,end_date,main_topic,subtopics,learning_objectives,curriculum_year,exam_window,exam_date,official_topic_weight,los_ids,reading_or_module_name,exam_phase",
                "1,2026-06-22,2026-06-28,Financial Statement Analysis,\"cash flow, ratios\",Recognize terms,2026,Feb 2027,2027-02-20,13,FSA-1,FSA Basics,learning",
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def frozen_now() -> dt.datetime:
    return dt.datetime(2026, 6, 24, 12, 0, tzinfo=dt.UTC)

