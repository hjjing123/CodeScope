from __future__ import annotations

import io
import mimetypes
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
    JobLogEntryPayload,
    JobLogPayload,
    JobListPayload,
    JobPayload,
    JobTriggerPayload,
    ScanJobCreateRequest,
)
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.artifact_service import (
    list_job_artifacts,
    resolve_job_artifact,
)
from app.services.authorization_service import ensure_project_action
from app.services.scan_service import (
    cancel_scan_job,
    clone_scan_job_for_retry,
    compute_scan_request_fingerprint,
    create_scan_job,
    dispatch_scan_job,
    failure_hint_for_code,
    get_existing_idempotent_scan_job,
    normalize_rule_set_ids,
    normalize_scan_mode,
)
from app.services.task_log_service import (
    build_task_logs_zip_bytes,
    build_task_stage_log_bytes,
    read_task_logs,
    sync_task_log_index,
)


router = APIRouter(tags=["jobs"])


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


def _job_payload(job: Job) -> JobPayload:
    return JobPayload(
        id=job.id,
        project_id=job.project_id,
        version_id=job.version_id,
        job_type=job.job_type,
        payload=job.payload,
        status=job.status,
        stage=job.stage,
        failure_code=job.failure_code,
        failure_stage=job.failure_stage,
        failure_category=job.failure_category,
        failure_hint=job.failure_hint or failure_hint_for_code(job.failure_code),
        result_summary=job.result_summary,
        created_by=job.created_by,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


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
    scan_mode = normalize_scan_mode(payload.scan_mode)
    normalized_rule_set_ids = normalize_rule_set_ids(payload.rule_set_ids)
    target_rule_id = (payload.target_rule_id or "").strip() or None

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
        raise AppError(code="NOT_FOUND", status_code=404, message="版本不存在")
    if version.project_id != payload.project_id:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="version_id 不属于当前项目",
        )
    if version.status != VersionStatus.READY.value:
        raise AppError(
            code="VERSION_NOT_READY", status_code=409, message="仅 READY 版本可发起扫描"
        )

    request_fingerprint = compute_scan_request_fingerprint(
        {
            "project_id": str(payload.project_id),
            "version_id": str(payload.version_id),
            "scan_mode": scan_mode,
            "rule_set_ids": normalized_rule_set_ids,
            "note": payload.note,
            "target_rule_id": target_rule_id,
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
            "scan_mode": scan_mode,
            "rule_set_ids": normalized_rule_set_ids,
            "note": payload.note,
            "target_rule_id": target_rule_id,
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
            "version_id": str(payload.version_id),
            "scan_mode": scan_mode,
            "rule_set_count": len(normalized_rule_set_ids),
            "target_rule_id": target_rule_id,
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

    rows_stmt = select(Job)
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = db.scalars(
        rows_stmt.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    data = JobListPayload(items=[_job_payload(item) for item in rows], total=total)
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
    return success_response(request, data=_job_payload(job).model_dump())


@router.get("/api/v1/jobs/{job_id}/logs")
def get_job_logs(
    request: Request,
    job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    tail: int = Query(default=200, ge=1, le=5000),
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
            code="INVALID_ARGUMENT", status_code=422, message="当前仅支持扫描任务日志"
        )

    sync_task_log_index(
        task_type="SCAN",
        task_id=job.id,
        project_id=job.project_id,
        db=db,
    )
    items = read_task_logs(task_type="SCAN", task_id=job_id, stage=stage, tail=tail)
    payload = JobLogPayload(
        job_id=job_id,
        items=[JobLogEntryPayload(**item) for item in items],
    )
    return success_response(request, data=payload.model_dump())


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
    if job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="当前仅支持扫描任务日志下载",
        )

    sync_task_log_index(
        task_type="SCAN",
        task_id=job.id,
        project_id=job.project_id,
        db=db,
    )

    if stage is not None and stage.strip():
        content = build_task_stage_log_bytes(
            task_type="SCAN",
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

    archive_bytes = build_task_logs_zip_bytes(task_type="SCAN", task_id=job_id)
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
