from __future__ import annotations

import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

from sqlalchemy.orm import sessionmaker

from app.models import TaskLogType
from app.services.import_service import run_import_job
from app.services.runtime_log_service import append_runtime_log
from app.services.rule_stats_service import run_rule_stats_aggregation
from app.services.scan_service import run_scan_job
from app.services.selftest_service import run_selftest_job
from app.worker.celery_app import celery_app


_local_executor = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="codescope-local-worker"
)
_local_futures: dict[str, Future[Any]] = {}
_local_future_lock = Lock()


def _task_context_from_kwargs(
    kwargs: dict[str, Any],
) -> tuple[str | None, uuid.UUID | None]:
    if "job_id" in kwargs:
        return TaskLogType.SCAN.value, _coerce_uuid(kwargs.get("job_id"))
    if "import_job_id" in kwargs:
        return TaskLogType.IMPORT.value, _coerce_uuid(kwargs.get("import_job_id"))
    if "selftest_job_id" in kwargs:
        return TaskLogType.SELFTEST.value, _coerce_uuid(kwargs.get("selftest_job_id"))
    return None, None


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _append_worker_runtime_log(
    *,
    db_bind: Any | None,
    level: str,
    event: str,
    message: str,
    task_type: str | None,
    task_id: uuid.UUID | None,
    error_code: str | None = None,
    detail_json: dict[str, object] | None = None,
) -> None:
    if db_bind is None:
        return

    scoped_session = sessionmaker(
        bind=db_bind,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = scoped_session()
    try:
        append_runtime_log(
            level=level,
            service="worker",
            module="worker.tasks",
            event=event,
            message=message,
            task_type=task_type,
            task_id=task_id,
            error_code=error_code,
            detail_json=detail_json or {},
            db=session,
        )
    finally:
        session.close()


def _submit_local_async(task_func: Callable[..., None], *args: Any) -> str:
    task_id = str(uuid.uuid4())
    future = _local_executor.submit(task_func, *args)
    with _local_future_lock:
        _local_futures[task_id] = future

    def _cleanup(_future: Future[Any]) -> None:
        with _local_future_lock:
            _local_futures.pop(task_id, None)

    future.add_done_callback(_cleanup)
    return task_id


def _run_with_bind(
    db_bind: Any | None, runner: Callable[..., None], **kwargs: Any
) -> None:
    task_type, task_id = _task_context_from_kwargs(kwargs)
    _append_worker_runtime_log(
        db_bind=db_bind,
        level="INFO",
        event="worker.task.started",
        message=f"worker task started: {runner.__name__}",
        task_type=task_type,
        task_id=task_id,
        detail_json={"runner": runner.__name__},
    )
    if db_bind is None:
        try:
            runner(**kwargs, db=None)
            _append_worker_runtime_log(
                db_bind=db_bind,
                level="INFO",
                event="worker.task.succeeded",
                message=f"worker task succeeded: {runner.__name__}",
                task_type=task_type,
                task_id=task_id,
                detail_json={"runner": runner.__name__},
            )
            return
        except Exception as exc:
            _append_worker_runtime_log(
                db_bind=db_bind,
                level="ERROR",
                event="worker.task.failed",
                message=f"worker task failed: {runner.__name__}",
                task_type=task_type,
                task_id=task_id,
                error_code=exc.__class__.__name__.upper(),
                detail_json={"runner": runner.__name__, "error": str(exc)},
            )
            raise

    scoped_session = sessionmaker(
        bind=db_bind, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = scoped_session()
    try:
        runner(**kwargs, db=session)
        _append_worker_runtime_log(
            db_bind=db_bind,
            level="INFO",
            event="worker.task.succeeded",
            message=f"worker task succeeded: {runner.__name__}",
            task_type=task_type,
            task_id=task_id,
            detail_json={"runner": runner.__name__},
        )
    except Exception as exc:
        _append_worker_runtime_log(
            db_bind=db_bind,
            level="ERROR",
            event="worker.task.failed",
            message=f"worker task failed: {runner.__name__}",
            task_type=task_type,
            task_id=task_id,
            error_code=exc.__class__.__name__.upper(),
            detail_json={"runner": runner.__name__, "error": str(exc)},
        )
        raise
    finally:
        session.close()


def _run_scan(job_id: str) -> None:
    _run_with_bind(None, run_scan_job, job_id=uuid.UUID(job_id))


def _run_import(import_job_id: str, db_bind: Any | None = None) -> None:
    _run_with_bind(db_bind, run_import_job, import_job_id=uuid.UUID(import_job_id))


def _run_rule_selftest(selftest_job_id: str, db_bind: Any | None = None) -> None:
    _run_with_bind(
        db_bind, run_selftest_job, selftest_job_id=uuid.UUID(selftest_job_id)
    )


def _run_rule_stats(job_id: str, db_bind: Any | None = None) -> None:
    _run_with_bind(db_bind, run_rule_stats_aggregation, job_id=uuid.UUID(job_id))


if celery_app is not None:

    @celery_app.task(name="scan.run_scan_job")
    def run_scan_job_task(job_id: str) -> None:
        _run_scan(job_id)

    @celery_app.task(name="import.run_import_job")
    def run_import_job_task(import_job_id: str) -> None:
        _run_import(import_job_id, None)

    @celery_app.task(name="rule.run_selftest_job")
    def run_rule_selftest_job_task(selftest_job_id: str) -> None:
        _run_rule_selftest(selftest_job_id, None)

    @celery_app.task(name="rule.aggregate_stats")
    def run_rule_stats_aggregation_task(job_id: str) -> None:
        _run_rule_stats(job_id, None)

else:

    def run_scan_job_task(job_id: str) -> None:
        _run_scan(job_id)

    def run_import_job_task(import_job_id: str) -> None:
        _run_import(import_job_id, None)

    def run_rule_selftest_job_task(selftest_job_id: str) -> None:
        _run_rule_selftest(selftest_job_id, None)

    def run_rule_stats_aggregation_task(job_id: str) -> None:
        _run_rule_stats(job_id, None)


def enqueue_scan_job(*, job_id: uuid.UUID) -> str | None:
    if celery_app is None:
        return None

    task = run_scan_job_task.delay(str(job_id))
    return str(task.id)


def enqueue_import_job(
    *, import_job_id: uuid.UUID, db_bind: Any | None = None
) -> str | None:
    if celery_app is not None:
        if bool(celery_app.conf.task_always_eager):
            return _submit_local_async(_run_import, str(import_job_id), db_bind)
        task = run_import_job_task.delay(str(import_job_id))
        return str(task.id)
    return None


def enqueue_rule_selftest_job(
    *, selftest_job_id: uuid.UUID, db_bind: Any | None = None
) -> str | None:
    if celery_app is not None:
        if bool(celery_app.conf.task_always_eager):
            return _submit_local_async(
                _run_rule_selftest, str(selftest_job_id), db_bind
            )
        task = run_rule_selftest_job_task.delay(str(selftest_job_id))
        return str(task.id)
    return _submit_local_async(_run_rule_selftest, str(selftest_job_id), db_bind)


def enqueue_rule_stats_aggregation(
    *, job_id: uuid.UUID, db_bind: Any | None = None
) -> str | None:
    if celery_app is not None:
        if bool(celery_app.conf.task_always_eager):
            return _submit_local_async(_run_rule_stats, str(job_id), db_bind)
        task = run_rule_stats_aggregation_task.delay(str(job_id))
        return str(task.id)
    return _submit_local_async(_run_rule_stats, str(job_id), db_bind)


def revoke_scan_job(*, task_id: str) -> bool:
    if celery_app is None:
        return False
    celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    return True
