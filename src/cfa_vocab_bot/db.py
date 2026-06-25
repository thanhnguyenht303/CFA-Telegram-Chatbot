from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings, get_settings


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or url.database in {None, ":memory:"}:
        return
    Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    _ensure_sqlite_parent(settings.database_url)
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )

    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or create_db_engine(), autoflush=False, expire_on_commit=False)


SessionLocal = create_session_factory()


@contextmanager
def session_scope(session_factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    factory = session_factory or SessionLocal
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

