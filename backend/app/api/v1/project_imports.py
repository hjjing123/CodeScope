from __future__ import annotations

import io
import json
import time
import uuid
from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import (
    require_project_action,
    require_project_resource_action,
)
from app.models import (
    ImportJob,
    ImportJobStage,
    ImportJobStatus,
    ImportType,
    Project,
)
from app.schemas.import_job import (
    GitImportRequest,
    ImportJobProgressPayload,
    GitImportTestPayload,
    GitImportTestRequest,
    ImportJobPayload,
    ImportJobTriggerPayload,
)
from app.schemas.task_log import TaskLogEntryPayload, TaskLogPayload
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.import_service import (
    build_import_progress_payload,
    build_import_result_summary,
    compute_request_fingerprint,
    create_import_job,
    failure_hint_for_code,
    dispatch_import_job,
    get_existing_idempotent_import_job,
    mark_import_job_dispatch_failed,
    normalize_git_auth_settings,
    serialize_git_auth_payload,
    test_git_source,
)
from app.services.task_log_service import (
    build_task_logs_zip_bytes,
    build_task_stage_log_bytes,
    read_task_log_events,
    read_task_logs,
    sync_task_log_index,
)


router = APIRouter(tags=["project-imports"])

UPLOAD_COPY_CHUNK_BYTES = 8 * 1024 * 1024

PUBLIC_IMPORT_PAYLOAD_KEYS = {
    "request_id",
    "original_filename",
    "version_name",
    "note",
    "size_bytes",
    "repo_url",
    "repo_visibility",
    "auth_type",
    "ref_type",
    "ref_value",
    "resolved_ref_type",
    "resolved_ref_value",
    "resolved_ref",
    "auto_detected_ref",
    "credential_id",
    "sync",
    "dispatch",
}


def _upload_archive_suffix(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".zip"):
        return ".zip"
    if lower.endswith(".tar.gz"):
        return ".tar.gz"
    if lower.endswith(".tgz"):
        return ".tgz"
    raise AppError(
        code="ARCHIVE_INVALID", status_code=422, message="仅支持 zip/tar.gz 文件"
    )


def _save_upload_to_workspace(
    *, job_id: uuid.UUID, upload: UploadFile
) -> tuple[Path, int]:
    settings = get_settings()
    filename = upload.filename or "upload.zip"
    suffix = _upload_archive_suffix(filename)
    workspace = Path(settings.import_workspace_root) / str(job_id)
    workspace.mkdir(parents=True, exist_ok=True)
    archive_path = workspace / f"upload{suffix}"

    total = 0
    with archive_path.open("wb") as destination:
        while True:
            chunk = upload.file.read(UPLOAD_COPY_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.import_upload_max_bytes:
                raise AppError(
                    code="UPLOAD_TOO_LARGE",
                    status_code=413,
                    message="上传文件超出大小限制",
                )
            destination.write(chunk)

    return archive_path, total


def _import_job_payload(job: ImportJob) -> ImportJobPayload:
    payload: dict[str, object] = {}
    if isinstance(job.payload, dict):
        payload = {
            key: value
            for key, value in job.payload.items()
            if key in PUBLIC_IMPORT_PAYLOAD_KEYS
        }

    return ImportJobPayload(
        id=job.id,
        project_id=job.project_id,
        version_id=job.version_id,
        import_type=job.import_type,
        payload=payload,
        status=job.status,
        stage=job.stage,
        progress=ImportJobProgressPayload(**build_import_progress_payload(job)),
        result_summary=build_import_result_summary(job),
        failure_code=job.failure_code,
        failure_hint=failure_hint_for_code(job.failure_code),
        created_by=job.created_by,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _ensure_project_importable(db: Session, *, project_id: uuid.UUID) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")


def _idempotency_replay_payload(job: ImportJob) -> ImportJobTriggerPayload:
    return ImportJobTriggerPayload(import_job_id=job.id, idempotent_replay=True)


def _normalize_idempotency_key(idempotency_key: str | None) -> str | None:
    normalized = (idempotency_key or "").strip()
    if not normalized:
        return None
    if len(normalized) > 128:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="Idempotency-Key 长度不能超过 128",
        )
    return normalized


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


@router.post("/api/v1/projects/{project_id}/imports/upload")
def import_upload(
    request: Request,
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    version_name: str | None = Query(default=None),
    note: str | None = Query(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    request_id = get_request_id(request)
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    original_filename = file.filename or "upload.zip"
    _ensure_project_importable(db, project_id=project_id)

    request_fingerprint = compute_request_fingerprint(
        {
            "import_type": ImportType.UPLOAD.value,
            "original_filename": original_filename,
            "version_name": version_name,
            "note": note,
        }
    )
    existing_job = get_existing_idempotent_import_job(
        db,
        project_id=project_id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing_job is not None:
        return success_response(
            request,
            data=_idempotency_replay_payload(existing_job).model_dump(),
            status_code=200,
        )

    job = create_import_job(
        db,
        project_id=project_id,
        import_type=ImportType.UPLOAD.value,
        payload={
            "request_id": request_id,
            "original_filename": original_filename,
            "version_name": version_name,
            "note": note,
        },
        created_by=principal.user.id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )

    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="import.upload.triggered",
        resource_type="IMPORT_JOB",
        resource_id=str(job.id),
        project_id=project_id,
        detail_json={"filename": original_filename, "version_name": version_name},
    )
    db.commit()

    try:
        archive_path, size_bytes = _save_upload_to_workspace(job_id=job.id, upload=file)
    except AppError as exc:
        shutil.rmtree(
            Path(get_settings().import_workspace_root) / str(job.id), ignore_errors=True
        )
        failed_job = db.get(ImportJob, job.id)
        if failed_job is not None:
            failed_job.status = ImportJobStatus.FAILED.value
            failed_job.stage = ImportJobStage.VALIDATE.value
            failed_job.failure_code = exc.code
            append_audit_log(
                db,
                request_id=request_id,
                operator_user_id=principal.user.id,
                action="import.upload.failed",
                resource_type="IMPORT_JOB",
                resource_id=str(failed_job.id),
                project_id=project_id,
                result="FAILED",
                error_code=exc.code,
            )
            db.commit()
        raise

    refreshed = db.get(ImportJob, job.id)
    if refreshed is not None:
        refreshed.payload = {
            **(refreshed.payload or {}),
            "archive_path": str(archive_path),
            "size_bytes": size_bytes,
        }
        db.commit()

    try:
        dispatch_import_job(db, job=job)
    except AppError as exc:
        if exc.code == "IMPORT_DISPATCH_FAILED":
            shutil.rmtree(
                Path(get_settings().import_workspace_root) / str(job.id),
                ignore_errors=True,
            )
            mark_import_job_dispatch_failed(
                db,
                job_id=job.id,
                request_id=request_id,
                operator_user_id=principal.user.id,
            )
        raise

    data = ImportJobTriggerPayload(import_job_id=job.id, idempotent_replay=False)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.post("/api/v1/projects/{project_id}/imports/git")
def import_git(
    request: Request,
    project_id: uuid.UUID,
    payload: GitImportRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    request_id = get_request_id(request)
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    _ensure_project_importable(db, project_id=project_id)
    auth_settings = normalize_git_auth_settings(
        repo_url=payload.repo_url,
        repo_visibility=payload.repo_visibility,
        auth_type=payload.auth_type,
        username=payload.username,
        access_token=payload.access_token,
        ssh_private_key=payload.ssh_private_key,
        ssh_passphrase=payload.ssh_passphrase,
        credential_id=payload.credential_id,
    )
    sanitized_repo_url = str(auth_settings.get("repo_url_display") or payload.repo_url)
    serialized_auth_payload = serialize_git_auth_payload(auth_settings)

    request_fingerprint = compute_request_fingerprint(
        {
            "import_type": ImportType.GIT.value,
            "repo_url": payload.repo_url,
            "repo_visibility": auth_settings.get("repo_visibility"),
            "auth_type": auth_settings.get("auth_type"),
            "username": auth_settings.get("username"),
            "access_token": auth_settings.get("access_token"),
            "ssh_private_key": auth_settings.get("ssh_private_key"),
            "ssh_passphrase": auth_settings.get("ssh_passphrase"),
            "ref_type": payload.ref_type,
            "ref_value": payload.ref_value,
            "version_name": payload.version_name,
            "note": payload.note,
            "credential_id": payload.credential_id,
            "sync": False,
        }
    )
    existing_job = get_existing_idempotent_import_job(
        db,
        project_id=project_id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing_job is not None:
        return success_response(
            request,
            data=_idempotency_replay_payload(existing_job).model_dump(),
            status_code=200,
        )

    job = create_import_job(
        db,
        project_id=project_id,
        import_type=ImportType.GIT.value,
        payload={
            "request_id": request_id,
            "repo_url": sanitized_repo_url,
            "repo_url_internal": str(
                auth_settings.get("repo_url_internal") or payload.repo_url
            ),
            **serialized_auth_payload,
            "ref_type": payload.ref_type,
            "ref_value": payload.ref_value,
            "credential_id": payload.credential_id,
            "version_name": payload.version_name,
            "note": payload.note,
        },
        created_by=principal.user.id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="import.git.triggered",
        resource_type="IMPORT_JOB",
        resource_id=str(job.id),
        project_id=project_id,
        detail_json={"repo_url": sanitized_repo_url, "ref_value": payload.ref_value},
    )
    db.commit()

    try:
        dispatch_import_job(db, job=job)
    except AppError as exc:
        if exc.code == "IMPORT_DISPATCH_FAILED":
            mark_import_job_dispatch_failed(
                db,
                job_id=job.id,
                request_id=request_id,
                operator_user_id=principal.user.id,
            )
        raise

    data = ImportJobTriggerPayload(import_job_id=job.id, idempotent_replay=False)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.post("/api/v1/projects/{project_id}/imports/git/test")
def import_git_test(
    request: Request,
    project_id: uuid.UUID,
    payload: GitImportTestRequest,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    _ensure_project_importable(db, project_id=project_id)
    auth_settings = normalize_git_auth_settings(
        repo_url=payload.repo_url,
        repo_visibility=payload.repo_visibility,
        auth_type=payload.auth_type,
        username=payload.username,
        access_token=payload.access_token,
        ssh_private_key=payload.ssh_private_key,
        ssh_passphrase=payload.ssh_passphrase,
        credential_id=payload.credential_id,
    )

    resolved_ref = test_git_source(
        repo_url=payload.repo_url,
        ref_type=payload.ref_type,
        ref_value=payload.ref_value,
        git_auth=auth_settings,
    )
    data = GitImportTestPayload(
        ok=True,
        resolved_ref=str(resolved_ref.get("resolved_ref") or ""),
        resolved_ref_type=str(resolved_ref.get("resolved_ref_type") or ""),
        resolved_ref_value=str(resolved_ref.get("resolved_ref_value") or ""),
        auto_detected=bool(resolved_ref.get("auto_detected")),
    )
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/projects/{project_id}/imports/git/sync")
def import_git_sync(
    request: Request,
    project_id: uuid.UUID,
    note: str | None = Query(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    request_id = get_request_id(request)
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    _ensure_project_importable(db, project_id=project_id)

    request_fingerprint = compute_request_fingerprint(
        {
            "import_type": ImportType.GIT.value,
            "sync": True,
            "note": note,
        }
    )
    existing_job = get_existing_idempotent_import_job(
        db,
        project_id=project_id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if existing_job is not None:
        return success_response(
            request,
            data=_idempotency_replay_payload(existing_job).model_dump(),
            status_code=200,
        )

    job = create_import_job(
        db,
        project_id=project_id,
        import_type=ImportType.GIT.value,
        payload={"request_id": request_id, "note": note, "sync": True},
        created_by=principal.user.id,
        idempotency_key=normalized_idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="import.git.sync.triggered",
        resource_type="IMPORT_JOB",
        resource_id=str(job.id),
        project_id=project_id,
    )
    db.commit()

    try:
        dispatch_import_job(db, job=job)
    except AppError as exc:
        if exc.code == "IMPORT_DISPATCH_FAILED":
            mark_import_job_dispatch_failed(
                db,
                job_id=job.id,
                request_id=request_id,
                operator_user_id=principal.user.id,
            )
        raise
    data = ImportJobTriggerPayload(import_job_id=job.id, idempotent_replay=False)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.get("/api/v1/import-jobs/{job_id}")
def get_import_job(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="IMPORT_JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="导入任务不存在")
    return success_response(request, data=_import_job_payload(job).model_dump())


@router.get("/api/v1/import-jobs/{job_id}/logs")
def get_import_job_logs(
    request: Request,
    job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    tail: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="IMPORT_JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="导入任务不存在")

    sync_task_log_index(
        task_type="IMPORT",
        task_id=job.id,
        project_id=job.project_id,
        db=db,
    )

    items = read_task_logs(task_type="IMPORT", task_id=job.id, stage=stage, tail=tail)
    payload = TaskLogPayload(
        task_type="IMPORT",
        task_id=job.id,
        items=[TaskLogEntryPayload(**item) for item in items],
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/import-jobs/{job_id}/logs/stream")
def stream_import_job_logs(
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
            resource_type="IMPORT_JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="导入任务不存在")

    terminal_statuses = {
        ImportJobStatus.SUCCEEDED.value,
        ImportJobStatus.FAILED.value,
        ImportJobStatus.CANCELED.value,
        ImportJobStatus.TIMEOUT.value,
    }

    def stream():
        current_seq = seq
        started_at = time.monotonic()
        while True:
            sync_task_log_index(
                task_type="IMPORT",
                task_id=job.id,
                project_id=job.project_id,
                db=db,
            )
            events = read_task_log_events(
                task_type="IMPORT",
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
            latest_job = db.get(ImportJob, job.id)
            if latest_job is None:
                break
            if latest_job.status in terminal_statuses:
                yield _encode_sse_event(
                    event="done",
                    data={
                        "seq": current_seq,
                        "job_id": str(job.id),
                        "status": latest_job.status,
                        "stage": latest_job.stage,
                    },
                    event_id=current_seq,
                )
                break
            if time.monotonic() - started_at >= max_wait_seconds:
                yield _encode_sse_event(
                    event="keepalive",
                    data={
                        "seq": current_seq,
                        "job_id": str(job.id),
                        "status": latest_job.status,
                        "stage": latest_job.stage,
                    },
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


@router.get("/api/v1/import-jobs/{job_id}/logs/download")
def download_import_job_logs(
    request: Request,
    job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read",
            resource_type="IMPORT_JOB",
            resource_id_param="job_id",
        )
    ),
):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="导入任务不存在")

    sync_task_log_index(
        task_type="IMPORT",
        task_id=job.id,
        project_id=job.project_id,
        db=db,
    )

    if stage is not None and stage.strip():
        content = build_task_stage_log_bytes(
            task_type="IMPORT",
            task_id=job.id,
            stage=stage.strip(),
        )
        filename = f"{job.id}_{stage.strip()}.log"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    archive_bytes = build_task_logs_zip_bytes(task_type="IMPORT", task_id=job.id)
    filename = f"import_job_{job.id}_logs.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(archive_bytes), media_type="application/zip", headers=headers
    )
