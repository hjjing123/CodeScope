from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_principal, require_project_resource_action
from app.models import Finding, Job, Report, ReportType, SystemRole, UserProjectRole
from app.schemas.report import (
    ReportContentPayload,
    ReportDeletePayload,
    ReportJobCreateRequest,
    ReportJobTriggerPayload,
    ReportListPayload,
)
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.authorization_service import ensure_project_action
from app.services.report_service import (
    build_report_payload,
    create_report_job,
    delete_report_record,
    dispatch_report_job,
    get_report_download_path,
    mark_report_dispatch_failed,
    prepare_report_selection,
    read_report_markdown_content,
)


router = APIRouter(tags=["reports"])


def _validate_report_type(report_type: str | None) -> str | None:
    if report_type is None:
        return None
    normalized = report_type.strip().upper()
    allowed = {item.value for item in ReportType}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="report_type 值不合法",
            detail={"allowed_report_types": sorted(allowed)},
        )
    return normalized


@router.post("/api/v1/report-jobs")
def create_report_job_endpoint(
    request: Request,
    payload: ReportJobCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    request_id = get_request_id(request)
    ensure_project_action(
        db=db,
        user_id=principal.user.id,
        role=principal.user.role,
        project_id=payload.project_id,
        action="report:generate",
    )
    selection = prepare_report_selection(
        db,
        project_id=payload.project_id,
        version_id=payload.version_id,
        job_id=payload.job_id,
        report_type=payload.report_type,
        finding_id=payload.finding_id,
    )

    job = create_report_job(
        db,
        project_id=payload.project_id,
        version_id=payload.version_id,
        payload={
            "request_id": request_id,
            "report_type": payload.report_type,
            "scan_job_id": str(selection.scan_job.id),
            "finding_id": str(selection.target_finding_id)
            if selection.target_finding_id is not None
            else None,
            "options": payload.options.model_dump(),
        },
        created_by=principal.user.id,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="report.triggered",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=payload.project_id,
        detail_json={
            "report_type": payload.report_type,
            "scan_job_id": str(selection.scan_job.id),
            "target_finding_id": str(selection.target_finding_id)
            if selection.target_finding_id is not None
            else None,
            "finding_count": selection.finding_count,
        },
    )
    db.commit()

    try:
        dispatch_report_job(db, job=job)
    except AppError as exc:
        if exc.code == "REPORT_DISPATCH_FAILED":
            mark_report_dispatch_failed(
                db,
                job_id=job.id,
                request_id=request_id,
                operator_user_id=principal.user.id,
            )
        raise

    data = ReportJobTriggerPayload(
        report_job_id=job.id,
        report_type=selection.report_type,
        finding_count=selection.finding_count,
    )
    return success_response(request, data=data.model_dump(), status_code=202)


@router.get("/api/v1/reports")
def list_reports(
    request: Request,
    project_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    report_job_id: uuid.UUID | None = None,
    finding_id: uuid.UUID | None = None,
    report_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    normalized_report_type = _validate_report_type(report_type)
    conditions = []
    if project_id is not None:
        conditions.append(Report.project_id == project_id)
    if version_id is not None:
        conditions.append(Report.version_id == version_id)
    if job_id is not None:
        conditions.append(Report.job_id == job_id)
    if report_job_id is not None:
        conditions.append(Report.report_job_id == report_job_id)
    if finding_id is not None:
        conditions.append(Report.finding_id == finding_id)
    if normalized_report_type is not None:
        conditions.append(Report.report_type == normalized_report_type)

    if principal.user.role != SystemRole.ADMIN.value:
        if project_id is not None:
            ensure_project_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                project_id=project_id,
                action="report:read",
            )
        else:
            conditions.append(
                Report.project_id.in_(
                    select(UserProjectRole.project_id).where(
                        UserProjectRole.user_id == principal.user.id
                    )
                )
            )

    total_stmt = select(func.count()).select_from(Report)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = db.scalar(total_stmt) or 0

    rows_stmt = select(Report)
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    reports = db.scalars(
        rows_stmt.order_by(Report.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    finding_ids = [item.finding_id for item in reports if item.finding_id is not None]
    finding_map: dict[uuid.UUID, Finding] = {}
    if finding_ids:
        finding_rows = db.scalars(
            select(Finding).where(Finding.id.in_(finding_ids))
        ).all()
        finding_map = {item.id: item for item in finding_rows}

    scan_job_ids = [item.job_id for item in reports if item.job_id is not None]
    job_map: dict[uuid.UUID, Job] = {}
    finding_count_map: dict[uuid.UUID, int] = {}
    if scan_job_ids:
        job_rows = db.scalars(select(Job).where(Job.id.in_(scan_job_ids))).all()
        job_map = {item.id: item for item in job_rows}
        count_rows = db.execute(
            select(Finding.job_id, func.count(Finding.id))
            .where(Finding.job_id.in_(scan_job_ids))
            .group_by(Finding.job_id)
        ).all()
        finding_count_map = {job_id: int(count) for job_id, count in count_rows}

    data = ReportListPayload(
        items=[
            build_report_payload(
                report,
                finding=finding_map.get(report.finding_id),
                scan_job=job_map.get(report.job_id),
                finding_count=finding_count_map.get(report.job_id),
            )
            for report in reports
        ],
        total=total,
    )
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/reports/{report_id}")
def get_report(
    request: Request,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "report:read",
            resource_type="REPORT",
            resource_id_param="report_id",
        )
    ),
):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="报告不存在")
    finding = (
        db.get(Finding, report.finding_id) if report.finding_id is not None else None
    )
    scan_job = db.get(Job, report.job_id) if report.job_id is not None else None
    finding_count = (
        db.scalar(select(func.count(Finding.id)).where(Finding.job_id == report.job_id))
        if report.report_type == ReportType.SCAN.value and report.job_id is not None
        else None
    )
    return success_response(
        request,
        data=build_report_payload(
            report,
            finding=finding,
            scan_job=scan_job,
            finding_count=int(finding_count) if finding_count is not None else None,
        ).model_dump(),
    )


@router.get("/api/v1/reports/{report_id}/content")
def get_report_content(
    request: Request,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "report:read",
            resource_type="REPORT",
            resource_id_param="report_id",
        )
    ),
):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="报告不存在")
    finding = (
        db.get(Finding, report.finding_id) if report.finding_id is not None else None
    )
    scan_job = db.get(Job, report.job_id) if report.job_id is not None else None
    finding_count = (
        db.scalar(select(func.count(Finding.id)).where(Finding.job_id == report.job_id))
        if report.report_type == ReportType.SCAN.value and report.job_id is not None
        else None
    )
    data = ReportContentPayload(
        report=build_report_payload(
            report,
            finding=finding,
            scan_job=scan_job,
            finding_count=int(finding_count) if finding_count is not None else None,
        ),
        content=read_report_markdown_content(report=report),
    )
    return success_response(request, data=data.model_dump())


@router.delete("/api/v1/reports/{report_id}")
def delete_report(
    request: Request,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "report:delete",
            resource_type="REPORT",
            resource_id_param="report_id",
        )
    ),
):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="报告不存在")

    report_title = str(report.title or "").strip() or None
    summary = delete_report_record(db, report=report)
    payload = ReportDeletePayload(**summary)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="report.deleted",
        resource_type="REPORT",
        resource_id=str(report_id),
        project_id=report.project_id,
        detail_json={
            "report_type": report.report_type,
            "report_title": report_title,
            "report_job_id": str(report.report_job_id)
            if report.report_job_id
            else None,
            "remaining_report_count": payload.remaining_report_count,
            "deleted_report_file": payload.deleted_report_file,
            "deleted_report_job_root": payload.deleted_report_job_root,
            "deleted_report_job_files_count": payload.deleted_report_job_files_count,
            "deleted_task_log_index_count": payload.deleted_task_log_index_count,
            "deleted_log_files_count": payload.deleted_log_files_count,
        },
    )
    db.commit()
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/reports/{report_id}/download")
def download_report(
    request: Request,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "report:read",
            resource_type="REPORT",
            resource_id_param="report_id",
        )
    ),
):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="报告不存在")
    file_name, path = get_report_download_path(report=report)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="report.downloaded",
        resource_type="REPORT",
        resource_id=str(report.id),
        project_id=report.project_id,
        detail_json={
            "file_name": file_name,
            "report_job_id": str(report.report_job_id)
            if report.report_job_id
            else None,
        },
    )
    db.commit()
    media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    return FileResponse(path=path, media_type=media_type, filename=file_name)
