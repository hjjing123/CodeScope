from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobStreamEvent


def append_job_stream_event(
    db: Session,
    *,
    job_id: uuid.UUID,
    project_id: uuid.UUID | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> int:
    event = JobStreamEvent(
        job_id=job_id,
        project_id=project_id,
        event_type=str(event_type or "message").strip() or "message",
        payload_json=dict(payload or {}),
    )
    db.add(event)
    db.flush()
    return int(event.id)


def list_job_stream_events(
    db: Session,
    *,
    job_id: uuid.UUID,
    after_id: int = 0,
    limit: int = 200,
) -> list[JobStreamEvent]:
    safe_after_id = max(0, int(after_id))
    safe_limit = min(max(1, int(limit)), 2000)
    return db.scalars(
        select(JobStreamEvent)
        .where(JobStreamEvent.job_id == job_id, JobStreamEvent.id > safe_after_id)
        .order_by(JobStreamEvent.id.asc())
        .limit(safe_limit)
    ).all()


def serialize_job_stream_event(event: JobStreamEvent) -> dict[str, Any]:
    return {
        "id": int(event.id),
        "job_id": str(event.job_id),
        "project_id": str(event.project_id) if event.project_id is not None else None,
        "event_type": event.event_type,
        "payload": dict(event.payload_json or {}),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
