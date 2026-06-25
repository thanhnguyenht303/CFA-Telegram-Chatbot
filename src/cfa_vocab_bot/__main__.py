from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from cfa_vocab_bot.admin_api import create_api_app
from cfa_vocab_bot.bot import run_bot
from cfa_vocab_bot.config import get_settings
from cfa_vocab_bot.db import create_db_engine, create_session_factory
from cfa_vocab_bot.logging_config import configure_logging
from cfa_vocab_bot.models import Base
from cfa_vocab_bot.services.importers import import_timeline
from cfa_vocab_bot.services.seed import seed_vocab_from_json


def _init_db() -> None:
    settings = get_settings()
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    print("Database initialized.")


def _seed(path: str) -> None:
    settings = get_settings()
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        count = seed_vocab_from_json(session, path)
        session.commit()
    print(f"Seeded {count} vocab items.")


def _import_timeline(path: str, user_id: int | None) -> None:
    settings = get_settings()
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        count, warnings = import_timeline(session, user_id=user_id, path=path)
        session.commit()
    print(f"Imported {count} timeline rows.")
    for warning in warnings:
        print(f"Warning: {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="cfa-vocab-bot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bot")
    api_parser = sub.add_parser("api")
    api_parser.add_argument("--host", default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=8000)
    sub.add_parser("init-db")
    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("path", nargs="?", default=str(Path("data") / "seed_vocab.json"))
    import_parser = sub.add_parser("import-timeline")
    import_parser.add_argument("path")
    import_parser.add_argument("--user-id", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)

    if args.command == "bot":
        run_bot(settings)
    elif args.command == "api":
        uvicorn.run(create_api_app(settings), host=args.host, port=args.port)
    elif args.command == "init-db":
        _init_db()
    elif args.command == "seed":
        _seed(args.path)
    elif args.command == "import-timeline":
        _import_timeline(args.path, args.user_id)


if __name__ == "__main__":
    main()

