from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import Job, JobStatus, ScanRuntimeLease


TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELED.value,
    JobStatus.TIMEOUT.value,
}


def acquire_scan_runtime_slot(
    *,
    job_id: uuid.UUID,
    db_bind: Any | None = None,
    on_wait: Callable[[int], None] | None = None,
) -> int:
    settings = get_settings()
    max_slots = max(
        1, int(getattr(settings, "scan_external_runtime_max_slots", 2) or 2)
    )
    wait_seconds = max(
        1,
        int(getattr(settings, "scan_external_runtime_slot_wait_seconds", 1) or 1),
    )
    timeout_seconds = max(
        wait_seconds,
        int(
            getattr(settings, "scan_external_runtime_slot_timeout_seconds", 3600)
            or 3600
        ),
    )
    deadline = time.monotonic() + timeout_seconds
    waited_rounds = 0
    session_factory = (
        sessionmaker(
            bind=db_bind,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        if db_bind is not None
        else SessionLocal
    )

    while True:
        with session_factory() as session:
            _reap_stale_scan_runtime_leases(session)
            job = session.get(Job, job_id)
            if job is None:
                raise AppError(
                    code="NOT_FOUND", status_code=404, message="扫描任务不存在"
                )
            if job.status in TERMINAL_JOB_STATUSES:
                raise AppError(
                    code="SCAN_CANCELED",
                    status_code=409,
                    message="扫描任务已结束，停止等待运行槽位",
                )

            existing = session.get(ScanRuntimeLease, job_id)
            if existing is not None:
                return int(existing.slot_index)

            for slot_index in range(1, max_slots + 1):
                session.add(ScanRuntimeLease(job_id=job_id, slot_index=slot_index))
                try:
                    session.commit()
                    return slot_index
                except IntegrityError:
                    session.rollback()

        waited_rounds += 1
        if on_wait is not None:
            on_wait(waited_rounds)
        if time.monotonic() >= deadline:
            raise AppError(
                code="SCAN_EXTERNAL_QUEUE_TIMEOUT",
                status_code=409,
                message="等待 Neo4j 运行槽位超时",
                detail={"max_slots": max_slots, "timeout_seconds": timeout_seconds},
            )
        time.sleep(wait_seconds)


def release_scan_runtime_slot(*, job_id: uuid.UUID, db_bind: Any | None = None) -> None:
    session_factory = (
        sessionmaker(
            bind=db_bind,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        if db_bind is not None
        else SessionLocal
    )
    with session_factory() as session:
        session.execute(
            delete(ScanRuntimeLease).where(ScanRuntimeLease.job_id == job_id)
        )
        session.commit()


def _reap_stale_scan_runtime_leases(session) -> None:
    leases = session.scalars(select(ScanRuntimeLease)).all()
    if not leases:
        return
    removed = False
    for lease in leases:
        job = session.get(Job, lease.job_id)
        if job is None or job.status in TERMINAL_JOB_STATUSES:
            session.delete(lease)
            removed = True
    if removed:
        session.commit()
