from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import SystemLog, SystemLogKind
from app.schemas.runtime_log import RuntimeLogListPayload, RuntimeLogPayload
from app.services.auth_service import AuthPrincipal


router = APIRouter(tags=["runtime-logs"])


def _payload(item: SystemLog) -> RuntimeLogPayload:
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


@router.get("/api/v1/runtime-logs")
def list_runtime_logs(
    request: Request,
    level: str | None = None,
    service: str | None = None,
    module: str | None = None,
    event: str | None = None,
    request_id: str | None = None,
    operator_user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    task_type: str | None = None,
    task_id: uuid.UUID | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:auditlog")),
):
    conditions = [SystemLog.log_kind == SystemLogKind.RUNTIME.value]
    if level is not None and level.strip():
        conditions.append(SystemLog.level == level.strip().upper())
    if service is not None and service.strip():
        conditions.append(SystemLog.service == service.strip().lower())
    if module is not None and module.strip():
        conditions.append(SystemLog.module == module.strip())
    if event is not None and event.strip():
        conditions.append(SystemLog.event == event.strip())
    if request_id is not None and request_id.strip():
        conditions.append(SystemLog.request_id == request_id.strip())
    if operator_user_id is not None:
        conditions.append(SystemLog.operator_user_id == operator_user_id)
    if project_id is not None:
        conditions.append(SystemLog.project_id == project_id)
    if task_type is not None and task_type.strip():
        conditions.append(SystemLog.task_type == task_type.strip().upper())
    if task_id is not None:
        conditions.append(SystemLog.task_id == task_id)
    if status_code is not None:
        conditions.append(SystemLog.status_code == status_code)
    if error_code is not None and error_code.strip():
        conditions.append(SystemLog.error_code == error_code.strip().upper())
    if start_time is not None:
        conditions.append(SystemLog.occurred_at >= start_time)
    if end_time is not None:
        conditions.append(SystemLog.occurred_at <= end_time)

    total_stmt = select(func.count()).select_from(SystemLog)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = db.scalar(total_stmt) or 0

    rows_stmt = select(SystemLog)
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = db.scalars(
        rows_stmt.order_by(SystemLog.occurred_at.desc(), SystemLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    payload = RuntimeLogListPayload(
        items=[_payload(item) for item in rows], total=total
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/runtime-logs/{log_id}")
def get_runtime_log(
    request: Request,
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:auditlog")),
):
    target = db.get(SystemLog, log_id)
    if target is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="运行日志不存在")
    if target.log_kind != SystemLogKind.RUNTIME.value:
        raise AppError(code="NOT_FOUND", status_code=404, message="运行日志不存在")
    return success_response(request, data=_payload(target).model_dump())
