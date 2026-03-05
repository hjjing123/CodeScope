from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import SystemLog, SystemLogKind
from app.schemas.audit_log import AuditLogListPayload, AuditLogPayload
from app.services.auth_service import AuthPrincipal


router = APIRouter(tags=["audit-logs"])


@router.get("/api/v1/audit-logs")
def list_audit_logs(
    request: Request,
    request_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    project_id: uuid.UUID | None = None,
    result: str | None = None,
    error_code: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:auditlog")),
):
    conditions = []
    conditions.append(SystemLog.log_kind == SystemLogKind.OPERATION.value)
    if request_id is not None and request_id.strip():
        conditions.append(SystemLog.request_id == request_id.strip())
    if actor_user_id is not None:
        conditions.append(SystemLog.operator_user_id == actor_user_id)
    if action is not None and action.strip():
        conditions.append(SystemLog.action == action.strip())
    if resource_type is not None and resource_type.strip():
        conditions.append(SystemLog.resource_type == resource_type.strip().upper())
    if project_id is not None:
        conditions.append(SystemLog.project_id == project_id)
    if result is not None and result.strip():
        conditions.append(SystemLog.result == result.strip().upper())
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

    payload = AuditLogListPayload(
        items=[
            AuditLogPayload(
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
            for item in rows
        ],
        total=total,
    )
    return success_response(request, data=payload.model_dump())
