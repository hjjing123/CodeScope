from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.errors import AppError
from app.models import (
    JobStep,
    JobStepStatus,
    Project,
    SystemRole,
    User,
    Version,
    VersionStatus,
)
from app.services.scan_service import (
    SCAN_STEP_DEFINITIONS,
    compute_scan_request_fingerprint,
    create_scan_job,
    update_scan_job_step_status,
)


def _seed_scan_scope(db_session):
    user = User(
        email=f"job-steps-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        display_name="Job Step Tester",
        role=SystemRole.USER.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    project = Project(name="job-steps-project", status="SCANNABLE")
    db_session.add(project)
    db_session.flush()

    version = Version(
        project_id=project.id,
        name="v1",
        source="UPLOAD",
        status=VersionStatus.READY.value,
        snapshot_object_key="snapshots/job-steps-v1.tar.gz",
    )
    db_session.add(version)
    db_session.flush()
    return user, project, version


def test_create_scan_job_initializes_job_steps(db_session):
    user, project, version = _seed_scan_scope(db_session)
    payload = {"request_id": "req-job-steps"}
    fingerprint = compute_scan_request_fingerprint(payload)

    job = create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        payload=payload,
        created_by=user.id,
        idempotency_key="idem-job-steps",
        request_fingerprint=fingerprint,
    )
    db_session.commit()

    items = db_session.scalars(
        select(JobStep).where(JobStep.job_id == job.id).order_by(JobStep.step_order)
    ).all()
    assert len(items) == len(SCAN_STEP_DEFINITIONS)
    assert all(item.status == JobStepStatus.PENDING.value for item in items)
    assert [item.step_key for item in items] == [
        item[0] for item in SCAN_STEP_DEFINITIONS
    ]
    assert [item.display_name for item in items] == [
        item[1] for item in SCAN_STEP_DEFINITIONS
    ]
    assert [item.step_order for item in items] == list(
        range(1, len(SCAN_STEP_DEFINITIONS) + 1)
    )


def test_update_scan_job_step_status_updates_timestamps_and_duration(db_session):
    user, project, version = _seed_scan_scope(db_session)
    payload = {"request_id": "req-job-step-status"}
    job = create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        payload=payload,
        created_by=user.id,
        idempotency_key=None,
        request_fingerprint=compute_scan_request_fingerprint(payload),
    )
    db_session.commit()

    first_step_key = SCAN_STEP_DEFINITIONS[0][0]
    running_step = update_scan_job_step_status(
        db_session,
        job_id=job.id,
        step_key=first_step_key,
        status=JobStepStatus.RUNNING.value,
    )
    assert running_step.status == JobStepStatus.RUNNING.value
    assert running_step.started_at is not None
    assert running_step.finished_at is None
    assert running_step.duration_ms is None

    finished_step = update_scan_job_step_status(
        db_session,
        job_id=job.id,
        step_key=first_step_key,
        status=JobStepStatus.SUCCEEDED.value,
        now=running_step.started_at + timedelta(seconds=2),
    )
    db_session.commit()

    assert finished_step.status == JobStepStatus.SUCCEEDED.value
    assert finished_step.finished_at is not None
    assert finished_step.duration_ms == 2000


def test_update_scan_job_step_status_handles_naive_started_at(db_session):
    user, project, version = _seed_scan_scope(db_session)
    payload = {"request_id": "req-job-step-naive"}
    job = create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        payload=payload,
        created_by=user.id,
        idempotency_key=None,
        request_fingerprint=compute_scan_request_fingerprint(payload),
    )
    db_session.commit()

    first_step_key = SCAN_STEP_DEFINITIONS[0][0]
    running_step = update_scan_job_step_status(
        db_session,
        job_id=job.id,
        step_key=first_step_key,
        status=JobStepStatus.RUNNING.value,
    )
    running_step.started_at = running_step.started_at.replace(tzinfo=None)
    db_session.commit()

    finished_step = update_scan_job_step_status(
        db_session,
        job_id=job.id,
        step_key=first_step_key,
        status=JobStepStatus.SUCCEEDED.value,
    )

    assert finished_step.finished_at is not None
    assert finished_step.duration_ms is not None
    assert finished_step.duration_ms >= 0


def test_update_scan_job_step_status_rejects_invalid_status(db_session):
    user, project, version = _seed_scan_scope(db_session)
    payload = {"request_id": "req-job-step-invalid"}
    job = create_scan_job(
        db_session,
        project_id=project.id,
        version_id=version.id,
        payload=payload,
        created_by=user.id,
        idempotency_key=None,
        request_fingerprint=compute_scan_request_fingerprint(payload),
    )
    db_session.commit()

    first_step_key = SCAN_STEP_DEFINITIONS[0][0]
    try:
        update_scan_job_step_status(
            db_session,
            job_id=job.id,
            step_key=first_step_key,
            status="invalid",
        )
    except AppError as exc:
        assert exc.code == "INVALID_ARGUMENT"
    else:
        raise AssertionError("expected AppError for invalid step status")

    pending_items = db_session.scalars(
        select(JobStep).where(
            JobStep.job_id == job.id,
            JobStep.status == JobStepStatus.PENDING.value,
        )
    )
    assert len(list(pending_items)) == len(SCAN_STEP_DEFINITIONS)
