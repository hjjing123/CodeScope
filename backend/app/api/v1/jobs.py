from __future__ import annotations

import io
import json
import mimetypes
import time
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_principal, require_project_resource_action
from app.models import (
    Job,
    JobStep,
    JobStatus,
    JobType,
    Project,
    SystemRole,
    UserProjectRole,
    Version,
    VersionStatus,
)
from app.schemas.job import (
    JobActionPayload,
    JobArtifactListPayload,
    JobArtifactPayload,
    JobDeletePayload,
    JobDeleteRequest,
    JobLogEntryPayload,
    JobLogPayload,
    JobListPayload,
    JobPayload,
    JobTriggerPayload,
    ScanJobCreateRequest,
)
from app.services.ai_service import build_scan_ai_payload, sanitize_job_payload
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.artifact_service import (
    list_job_artifacts,
    resolve_job_artifact,
)
from app.services.authorization_service import ensure_project_action
from app.services.job_stream_service import (
    list_job_stream_events,
    serialize_job_stream_event,
)
from app.services.rule_set_file_service import resolve_scan_rule_keys
from app.services.scan_service import (
    build_scan_progress_payload,
    build_scan_steps_payload,
    cancel_scan_job,
    clone_scan_job_for_retry,
    compute_scan_request_fingerprint,
    create_scan_job,
    delete_scan_job,
    dispatch_scan_job,
    failure_hint_for_code,
    get_existing_idempotent_scan_job,
    list_scan_job_steps,
    normalize_scan_delete_targets,
)
from app.services.task_log_service import (
    build_task_logs_zip_bytes,
    build_task_stage_log_bytes,
    read_task_log_events,
    read_task_logs,
    sync_task_log_index,
)


router = APIRouter(tags=["jobs"])


def _task_log_type_for_job(job: Job) -> str | None:
    if job.job_type == JobType.SCAN.value:
        return "SCAN"
    if job.job_type == JobType.AI.value:
        return "AI"
    return None


def _normalize_idempotency_key(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > 128:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="Idempotency-Key 长度不能超过 128",
        )
    return normalized


def _validate_job_type(job_type: str | None) -> str | None:
    if job_type is None:
        return None
    normalized = job_type.strip().upper()
    allowed = {item.value for item in JobType}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="job_type 值不合法",
            detail={"allowed_job_types": sorted(allowed)},
        )
    return normalized


def _validate_job_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().upper()
    allowed = {item.value for item in JobStatus}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="status 值不合法",
            detail={"allowed_statuses": sorted(allowed)},
        )
    return normalized


def _load_steps_by_job_ids(
    db: Session, *, job_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[JobStep]]:
    if not job_ids:
        return {}
    rows = db.scalars(
        select(JobStep)
        .where(JobStep.job_id.in_(job_ids))
        .order_by(JobStep.step_order.asc(), JobStep.created_at.asc())
    ).all()
    by_job_id: dict[uuid.UUID, list[JobStep]] = {job_id: [] for job_id in job_ids}
    for row in rows:
        by_job_id.setdefault(row.job_id, []).append(row)
    return by_job_id


def _job_payload(
    job: Job,
    *,
    steps: list[JobStep] | None = None,
    project_name: str | None = None,
    version_name: str | None = None,
) -> JobPayload:
    resolved_steps = steps if steps is not None else []
    return JobPayload(
        id=job.id,
        project_id=job.project_id,
        project_name=project_name,
        version_id=job.version_id,
        version_name=version_name,
        job_type=job.job_type,
        payload=sanitize_job_payload(job.payload),
        status=job.status,
        stage=job.stage,
        failure_code=job.failure_code,
        failure_stage=job.failure_stage,
        failure_category=job.failure_category,
        failure_hint=job.failure_hint or failure_hint_for_code(job.failure_code),
        progress=build_scan_progress_payload(
            steps=resolved_steps, job_status=job.status
        ),
        steps=build_scan_steps_payload(steps=resolved_steps),
        result_summary=job.result_summary,
        created_by=job.created_by,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _encode_sse_event(
    *,
    event: str,
    data: dict[str, object],
    event_id: int | None = None,
) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for chunk in payload.splitlines() or ["{}"]:
        lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


@router.post("/api/v1/scan-jobs")
def create_scan_job_endpoint(
    request: Request,
    payload: ScanJobCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    request_id = get_request_id(request)
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    (
        normalized_rule_set_keys,
        normalized_rule_keys,
        resolved_rule_keys,
    ) = resolve_scan_rule_keys(
        rule_set_keys=payload.rule_set_keys,
        rule_keys=payload.rule_keys,
    )

    ensure_project_action(
        db=db,
        user_id=principal.user.id,
        role=principal.user.role,
        project_id=payload.project_id,
        action="job:create",
    )

    project = db.get(Project, payload.project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    version = db.get(Version, payload.version_id)
    if version is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="代码快照不存在")
    if version.project_id != payload.project_id:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="version_id 不属于当前项目的代码快照",
        )
    if version.status != VersionStatus.READY.value:
        raise AppError(
            code="VERSION_NOT_READY",
            status_code=409,
            message="仅 READY 状态的代码快照可发起扫描",
        )

    request_fingerprint = compute_scan_request_fingerprint(
        {
            "project_id": str(payload.project_id),
            "version_id": str(payload.version_id),
            "rule_set_keys": normalized_rule_set_keys,
            "rule_keys": normalized_rule_keys,
            "resolved_rule_keys": resolved_rule_keys,
            "note": payload.note,
        }
    )
    existing_job = get_existing_idempotent_scan_job(
        db,
        project_id=payload.project_id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing_job is not None:
        data = JobTriggerPayload(job_id=existing_job.id, idempotent_replay=True)
        return success_response(request, data=data.model_dump(), status_code=200)

    job = create_scan_job(
        db,
        project_id=payload.project_id,
        version_id=payload.version_id,
        payload={
            "request_id": request_id,
            "rule_set_keys": normalized_rule_set_keys,
            "rule_keys": normalized_rule_keys,
            "resolved_rule_keys": resolved_rule_keys,
            "note": payload.note,
            **(
                {
                    "ai": build_scan_ai_payload(
                        db,
                        user_id=principal.user.id,
                        ai_enabled=payload.ai_enabled,
                        ai_source=payload.ai_source,
                        ai_provider_id=payload.ai_provider_id,
                        ai_model=payload.ai_model,
                    )
                }
                if payload.ai_enabled
                else {}
            ),
        },
        created_by=principal.user.id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="scan.triggered",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=payload.project_id,
        detail_json={
            "snapshot_id": str(payload.version_id),
            "version_id": str(payload.version_id),
            "rule_set_count": len(normalized_rule_set_keys),
            "rule_key_count": len(normalized_rule_keys),
            "resolved_rule_count": len(resolved_rule_keys),
        },
    )
    db.commit()

    dispatch_scan_job(db, job=job)
    data = JobTriggerPayload(job_id=job.id, idempotent_replay=False)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.get("/api/v1/jobs")
def list_jobs(
    request: Request,
    project_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    job_type: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    normalized_job_type = _validate_job_type(job_type)
    normalized_status = _validate_job_status(status)

    conditions = []
    if project_id is not None:
        conditions.append(Job.project_id == project_id)
    if version_id is not None:
        conditions.append(Job.version_id == version_id)
    if normalized_job_type is not None:
        conditions.append(Job.job_type == normalized_job_type)
    if normalized_status is not None:
        conditions.append(Job.status == normalized_status)

    if principal.user.role != SystemRole.ADMIN.value:
        if project_id is not None:
            ensure_project_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                project_id=project_id,
                action="job:read",
            )
        else:
            conditions.append(
                Job.project_id.in_(
                    select(UserProjectRole.project_id).where(
                        UserProjectRole.user_id == principal.user.id
                    )
                )
            )

    total_stmt = select(func.count()).select_from(Job)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = db.scalar(total_stmt) or 0

    rows_stmt = (
        select(Job, Project.name, Version.name)
        .outerjoin(Project, Project.id == Job.project_id)
        .outerjoin(Version, Version.id == Job.version_id)
    )
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = db.execute(
        rows_stmt.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    jobs = [item for item, _project_name, _version_name in rows]
    steps_by_job_id = _load_steps_by_job_ids(db, job_ids=[item.id for item in jobs])
    data = JobListPayload(
        items=[
            _job_payload(
                item,
                steps=steps_by_job_id.get(item.id, []),
                project_name=project_name,
                version_name=version_name,
            )
            for item, project_name, version_name in rows
        ],
        total=total,
    )
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/jobs/{job_id}")
def get_job(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    project_name = db.scalar(select(Project.name).where(Project.id == job.project_id))
    version_name = db.scalar(select(Version.name).where(Version.id == job.version_id))
    steps = list_scan_job_steps(db, job_id=job.id)
    return success_response(
        request,
        data=_job_payload(
            job,
            steps=steps,
            project_name=project_name,
            version_name=version_name,
        ).model_dump(),
    )


@router.get("/api/v1/jobs/{job_id}/logs")
def get_job_logs(
    request: Request,
    job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    tail: int = Query(default=200, ge=0, le=5000),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    task_log_type = _task_log_type_for_job(job)
    if task_log_type is None:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="当前任务类型不支持日志查看",
        )

    sync_task_log_index(
        task_type=task_log_type,
        task_id=job.id,
        project_id=job.project_id,
        db=db,
    )
    items = read_task_logs(
        task_type=task_log_type, task_id=job_id, stage=stage, tail=tail
    )
    payload = JobLogPayload(
        job_id=job_id,
        items=[JobLogEntryPayload(**item) for item in items],
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/jobs/{job_id}/logs/stream")
def stream_job_logs(
    request: Request,
    job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    seq: int = Query(default=0, ge=0),
    poll_interval_ms: int = Query(default=500, ge=100, le=5000),
    max_wait_seconds: int = Query(default=30, ge=1, le=300),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    task_log_type = _task_log_type_for_job(job)
    if task_log_type is None:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="当前任务类型不支持日志流"
        )

    terminal_statuses = {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TIMEOUT.value,
    }

    def stream():
        current_seq = seq
        started_at = time.monotonic()
        while True:
            sync_task_log_index(
                task_type=task_log_type,
                task_id=job.id,
                project_id=job.project_id,
                db=db,
            )
            events = read_task_log_events(
                task_type=task_log_type,
                task_id=job.id,
                stage=stage,
                after_seq=current_seq,
                limit=2000,
            )
            for event in events:
                current_seq = int(event["seq"])
                yield _encode_sse_event(
                    event="log",
                    data=event,
                    event_id=current_seq,
                )

            db.expire_all()
            latest_job = db.get(Job, job.id)
            if latest_job is None:
                break
            if latest_job.status in terminal_statuses:
                done_payload = {
                    "seq": current_seq,
                    "job_id": str(job.id),
                    "status": latest_job.status,
                    "stage": latest_job.stage,
                }
                yield _encode_sse_event(
                    event="done",
                    data=done_payload,
                    event_id=current_seq,
                )
                break

            if time.monotonic() - started_at >= max_wait_seconds:
                keepalive_payload = {
                    "seq": current_seq,
                    "job_id": str(job.id),
                    "status": latest_job.status,
                    "stage": latest_job.stage,
                }
                yield _encode_sse_event(
                    event="keepalive",
                    data=keepalive_payload,
                    event_id=current_seq,
                )
                break
            time.sleep(poll_interval_ms / 1000.0)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/api/v1/jobs/{job_id}/events/stream")
def stream_job_events(
    request: Request,
    job_id: uuid.UUID,
    after_id: int = Query(default=0, ge=0),
    poll_interval_ms: int = Query(default=500, ge=100, le=5000),
    max_wait_seconds: int = Query(default=30, ge=1, le=300),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    if job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="当前仅支持扫描任务事件流"
        )

    terminal_statuses = {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TIMEOUT.value,
    }

    def stream():
        current_id = after_id
        started_at = time.monotonic()
        while True:
            events = list_job_stream_events(
                db,
                job_id=job.id,
                after_id=current_id,
                limit=500,
            )
            for event in events:
                current_id = int(event.id)
                payload = serialize_job_stream_event(event)
                yield _encode_sse_event(
                    event=event.event_type,
                    data=payload,
                    event_id=current_id,
                )

            db.expire_all()
            latest_job = db.get(Job, job.id)
            if latest_job is None:
                break
            if latest_job.status in terminal_statuses:
                done_payload = {
                    "id": current_id,
                    "job_id": str(job.id),
                    "event_type": "done",
                    "payload": {
                        "status": latest_job.status,
                        "stage": latest_job.stage,
                    },
                    "created_at": None,
                }
                yield _encode_sse_event(
                    event="done",
                    data=done_payload,
                    event_id=current_id,
                )
                break

            if time.monotonic() - started_at >= max_wait_seconds:
                keepalive_payload = {
                    "id": current_id,
                    "job_id": str(job.id),
                    "event_type": "keepalive",
                    "payload": {
                        "status": latest_job.status,
                        "stage": latest_job.stage,
                    },
                    "created_at": None,
                }
                yield _encode_sse_event(
                    event="keepalive",
                    data=keepalive_payload,
                    event_id=current_id,
                )
                break
            time.sleep(poll_interval_ms / 1000.0)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/api/v1/jobs/{job_id}/logs/download")
def download_job_logs(
    request: Request,
    job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    task_log_type = _task_log_type_for_job(job)
    if task_log_type is None:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="当前任务类型不支持日志下载",
        )

    sync_task_log_index(
        task_type=task_log_type,
        task_id=job.id,
        project_id=job.project_id,
        db=db,
    )

    if stage is not None and stage.strip():
        content = build_task_stage_log_bytes(
            task_type=task_log_type,
            task_id=job_id,
            stage=stage.strip(),
        )
        filename = f"{job_id}_{stage.strip()}.log"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    archive_bytes = build_task_logs_zip_bytes(task_type=task_log_type, task_id=job_id)
    filename = f"job_{job_id}_logs.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(archive_bytes), media_type="application/zip", headers=headers
    )


@router.get("/api/v1/jobs/{job_id}/artifacts")
def list_artifacts(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")

    items = list_job_artifacts(job=job)
    payload = JobArtifactListPayload(
        job_id=job.id,
        items=[JobArtifactPayload(**item) for item in items],
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/jobs/{job_id}/artifacts/{artifact_id}/download")
def download_artifact(
    request: Request,
    job_id: uuid.UUID,
    artifact_id: str,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")

    target, payload = resolve_job_artifact(job=job, artifact_id=artifact_id)
    filename = str(payload["filename"])
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path=target, media_type=media_type, filename=filename)


@router.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:cancel",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    if job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="仅支持取消扫描任务"
        )
    updated = cancel_scan_job(
        db,
        job=job,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
    )
    data = JobActionPayload(ok=True, job_id=updated.id, status=updated.status)
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/jobs/{job_id}/retry")
def retry_job(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:retry",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    source_job = db.get(Job, job_id)
    if source_job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    if source_job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="仅支持重试扫描任务"
        )

    retried_job = clone_scan_job_for_retry(
        db,
        source_job=source_job,
        request_id=get_request_id(request),
        created_by=principal.user.id,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="scan.retry.triggered",
        resource_type="JOB",
        resource_id=str(retried_job.id),
        project_id=retried_job.project_id,
        detail_json={"retry_of_job_id": str(source_job.id)},
    )
    db.commit()

    dispatch_scan_job(db, job=retried_job)
    data = JobTriggerPayload(job_id=retried_job.id, idempotent_replay=False)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.post("/api/v1/jobs/{job_id}/delete")
def delete_job(
    request: Request,
    job_id: uuid.UUID,
    payload: JobDeleteRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:delete",
            resource_type="JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")

    summary = delete_scan_job(
        db,
        job=job,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        targets=normalize_scan_delete_targets(payload.targets),
    )
    data = JobDeletePayload(ok=True, job_id=job_id, **summary)
    return success_response(request, data=data.model_dump())
