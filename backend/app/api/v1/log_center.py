from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import SystemLog, SystemLogKind, TaskLogIndex, TaskLogType
from app.schemas.audit_log import AuditLogPayload
from app.schemas.log_center import LogCenterCorrelationPayload, TaskLogPreviewPayload
from app.schemas.runtime_log import RuntimeLogPayload
from app.services.auth_service import AuthPrincipal
from app.services.task_log_service import sync_task_log_index


router = APIRouter(tags=["log-center"])


def _runtime_payload(item: SystemLog) -> RuntimeLogPayload:
    return RuntimeLogPayload(
        id=item.id,
        occurred_at=item.occurred_at,
        level=item.level or "",
        service=item.service or "",
        module=item.module or "",
        event=item.event or "",
        message=item.message or "",
        request_id=item.request_id,
        operator_user_id=item.operator_user_id,
        project_id=item.project_id,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        task_type=item.task_type,
        task_id=item.task_id,
        status_code=item.status_code,
        duration_ms=item.duration_ms,
        error_code=item.error_code,
        detail_json=item.detail_json,
        created_at=item.created_at,
    )


def _audit_payload(item: SystemLog) -> AuditLogPayload:
    return AuditLogPayload(
        id=item.id,
        request_id=item.request_id,
        operator_user_id=item.operator_user_id,
        action=item.action or "",
        resource_type=item.resource_type or "",
        resource_id=item.resource_id or "",
        project_id=item.project_id,
        result=item.result or "",
        error_code=item.error_code,
        detail_json=item.detail_json,
        created_at=item.occurred_at,
    )


@router.get("/api/v1/log-center/correlation")
def correlate_logs(
    request: Request,
    request_id: str | None = None,
    task_type: str | None = None,
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:auditlog")),
):
    normalized_request_id = (request_id or "").strip()
    normalized_task_type = (task_type or "").strip().upper()
    if normalized_task_type and normalized_task_type not in {
        item.value for item in TaskLogType
    }:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="task_type 参数不合法",
            detail={"allowed_task_types": [item.value for item in TaskLogType]},
        )

    if not normalized_request_id and task_id is None and project_id is None:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="请至少提供 request_id、task_id 或 project_id 之一",
        )

    audit_conditions = []
    runtime_conditions = []
    task_conditions = []

    if normalized_request_id:
        audit_conditions.append(SystemLog.request_id == normalized_request_id)
        runtime_conditions.append(SystemLog.request_id == normalized_request_id)
    if project_id is not None:
        audit_conditions.append(SystemLog.project_id == project_id)
        runtime_conditions.append(SystemLog.project_id == project_id)
        task_conditions.append(TaskLogIndex.project_id == project_id)
    if task_id is not None:
        runtime_conditions.append(SystemLog.task_id == task_id)
        task_conditions.append(TaskLogIndex.task_id == task_id)
    if normalized_task_type:
        runtime_conditions.append(SystemLog.task_type == normalized_task_type)
        task_conditions.append(TaskLogIndex.task_type == normalized_task_type)
    if start_time is not None:
        audit_conditions.append(SystemLog.occurred_at >= start_time)
        runtime_conditions.append(SystemLog.occurred_at >= start_time)
        task_conditions.append(TaskLogIndex.updated_at >= start_time)
    if end_time is not None:
        audit_conditions.append(SystemLog.occurred_at <= end_time)
        runtime_conditions.append(SystemLog.occurred_at <= end_time)
        task_conditions.append(TaskLogIndex.updated_at <= end_time)

    if task_id is not None and normalized_task_type:
        sync_task_log_index(
            task_type=normalized_task_type,
            task_id=task_id,
            project_id=project_id,
            db=db,
        )

    audit_stmt = select(SystemLog).where(
        SystemLog.log_kind == SystemLogKind.OPERATION.value
    )
    if audit_conditions:
        audit_stmt = audit_stmt.where(*audit_conditions)
    audit_rows = db.scalars(
        audit_stmt.order_by(SystemLog.occurred_at.desc()).limit(limit)
    ).all()

    runtime_stmt = select(SystemLog).where(
        SystemLog.log_kind == SystemLogKind.RUNTIME.value
    )
    if runtime_conditions:
        runtime_stmt = runtime_stmt.where(*runtime_conditions)
    runtime_rows = db.scalars(
        runtime_stmt.order_by(
            SystemLog.occurred_at.desc(), SystemLog.created_at.desc()
        ).limit(limit)
    ).all()

    task_stmt = select(TaskLogIndex)
    if task_conditions:
        task_stmt = task_stmt.where(*task_conditions)
    task_rows = db.scalars(
        task_stmt.order_by(TaskLogIndex.updated_at.desc()).limit(limit)
    ).all()

    payload = LogCenterCorrelationPayload(
        audit_logs=[_audit_payload(item) for item in audit_rows],
        runtime_logs=[_runtime_payload(item) for item in runtime_rows],
        task_log_previews=[
            TaskLogPreviewPayload(
                task_type=item.task_type,
                task_id=str(item.task_id),
                stage=item.stage,
                line_count=item.line_count,
                size_bytes=int(item.size_bytes),
                updated_at=item.updated_at,
            )
            for item in task_rows
        ],
    )
    return success_response(request, data=payload.model_dump())
