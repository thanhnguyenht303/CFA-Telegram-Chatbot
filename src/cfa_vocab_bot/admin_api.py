from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from cfa_vocab_bot.config import Settings, get_settings
from cfa_vocab_bot.db import create_db_engine, create_session_factory
from cfa_vocab_bot.models import Base, User
from cfa_vocab_bot.services.progress import progress_snapshot


def create_api_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        engine = create_db_engine(settings)
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)

    app = FastAPI(title="CFA Vocab Bot Admin API", version="0.1.0")

    def get_db():
        with session_factory() as session:
            yield session

    def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
        if not settings.admin_api_key:
            raise HTTPException(status_code=403, detail="Admin API key is not configured.")
        if x_admin_token != settings.admin_api_key:
            raise HTTPException(status_code=401, detail="Invalid admin token.")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready(session: Session = Depends(get_db)) -> dict[str, str]:
        session.execute(text("select 1"))
        return {"status": "ready"}

    @app.get("/admin/users/{chat_id}/progress", dependencies=[Depends(require_admin)])
    def user_progress(chat_id: int, session: Session = Depends(get_db)):
        user = session.query(User).filter(User.chat_id == chat_id).one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return progress_snapshot(session, user).model_dump()

    return app


app = create_api_app()

