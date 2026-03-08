from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from starlette.requests import Request


def _install_overlapped_stub() -> None:
    module = ModuleType("_overlapped")
    module.INVALID_HANDLE_VALUE = -1
    module.ERROR_IO_PENDING = 997
    module.ERROR_NETNAME_DELETED = 64
    module.ERROR_OPERATION_ABORTED = 995
    module.ERROR_PIPE_BUSY = 231
    module.SO_UPDATE_ACCEPT_CONTEXT = 0x700B
    module.SO_UPDATE_CONNECT_CONTEXT = 0x7010

    class Overlapped:
        def __init__(self, *_args, **_kwargs):
            self.pending = False
            self.address = 0

        def getresult(self):
            raise OSError("overlapped operations are unavailable")

        def cancel(self):
            return None

    def _unavailable(*_args, **_kwargs):
        raise OSError("overlapped operations are unavailable")

    module.Overlapped = Overlapped
    module.CreateIoCompletionPort = _unavailable
    module.GetQueuedCompletionStatus = _unavailable
    module.RegisterWaitWithQueue = _unavailable
    module.UnregisterWait = lambda *_args, **_kwargs: None
    module.UnregisterWaitEx = lambda *_args, **_kwargs: None
    module.CreateEvent = lambda *_args, **_kwargs: 0
    module.ConnectPipe = _unavailable
    module.WSAConnect = _unavailable
    module.BindLocal = _unavailable
    sys.modules["_overlapped"] = module


def _ensure_windows_asyncio_importable() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import _overlapped  # noqa: F401
    except OSError:
        _install_overlapped_stub()
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_ensure_windows_asyncio_importable()


def _is_asyncio_init_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10022:
        return True
    if isinstance(exc, NameError) and "base_events" in str(exc):
        return True
    return False


@pytest.fixture()
def db_session():
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.base import Base
        from app.worker import tasks as worker_tasks
    except Exception as exc:
        if _is_asyncio_init_error(exc):
            pytest.skip("当前 Windows 环境 asyncio 初始化异常（WinError 10022）")
        raise

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
def client(db_session, celery_eager_mode):
    try:
        from fastapi.testclient import TestClient
        from app.db.session import get_db
        from app.main import app
    except Exception as exc:
        if _is_asyncio_init_error(exc):
            pytest.skip("当前 Windows 环境 asyncio 初始化异常（WinError 10022）")
        raise

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
    try:
        from app.worker.celery_app import celery_app
    except Exception as exc:
        if _is_asyncio_init_error(exc):
            yield
            return
        raise

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
    try:
        from app.config import get_settings
    except Exception as exc:
        if _is_asyncio_init_error(exc):
            yield
            return
        raise

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
