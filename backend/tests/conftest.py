from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.worker.celery_app import celery_app
from app.worker import tasks as worker_tasks


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    session = testing_session_local()

    try:
        yield session
    finally:
        pending_futures = list(worker_tasks._local_futures.values())
        for future in pending_futures:
            try:
                future.result(timeout=5)
            except Exception:
                pass

        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session, celery_eager_mode):
    def override_get_db(request: Request):
        request.state.db_session = db_session
        yield db_session
        request.state.db_session = None

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def celery_eager_mode():
    if celery_app is None:
        yield
        return

    old_eager = bool(celery_app.conf.task_always_eager)
    old_propagates = bool(celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        yield
    finally:
        celery_app.conf.task_always_eager = old_eager
        celery_app.conf.task_eager_propagates = old_propagates


@pytest.fixture(autouse=True)
def test_dispatch_settings():
    settings = get_settings()
    old_scan_backend = settings.scan_dispatch_backend
    old_scan_fallback = settings.scan_dispatch_fallback_to_sync
    settings.scan_dispatch_backend = "sync"
    settings.scan_dispatch_fallback_to_sync = True
    try:
        yield
    finally:
        settings.scan_dispatch_backend = old_scan_backend
        settings.scan_dispatch_fallback_to_sync = old_scan_fallback
