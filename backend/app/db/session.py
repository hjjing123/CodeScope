from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _create_engine() -> Engine:
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(settings.database_url, future=True, connect_args=connect_args)


engine = _create_engine()
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db(request: Request) -> Generator[Session, None, None]:
    existing = getattr(request.state, "db_session", None)
    if isinstance(existing, Session):
        yield existing
        return
    db = SessionLocal()
    request.state.db_session = db
    try:
        yield db
    finally:
        request.state.db_session = None
        db.close()
