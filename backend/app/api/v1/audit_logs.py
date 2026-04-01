from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_principal
from app.models import SystemLog, SystemLogKind, SystemRole
from app.schemas.audit_log import AuditLogListPayload, AuditLogPayload
from app.services.auth_service import AuthPrincipal
from app.services.log_center_service import (
    build_log_keyword_condition,
    coalesce_json,
    normalize_action_groups,
    resolve_action_zh,
    resolve_summary_zh,
)


router = APIRouter(tags=["audit-logs"])


@router.get("/api/v1/audit-logs")
def list_audit_logs(
    request: Request,
    request_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    result: str | None = None,
    keyword: str | None = None,
    action_group: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    conditions = []
    conditions.append(SystemLog.log_kind == SystemLogKind.OPERATION.value)
    if request_id is not None and request_id.strip():
        conditions.append(SystemLog.request_id == request_id.strip())
    if actor_user_id is not None:
        conditions.append(SystemLog.operator_user_id == actor_user_id)
    if principal.user.role != SystemRole.ADMIN.value:
        conditions.append(SystemLog.operator_user_id == principal.user.id)
    if resource_type is not None and resource_type.strip():
        conditions.append(SystemLog.resource_type == resource_type.strip().upper())
    if result is not None and result.strip():
        conditions.append(SystemLog.result == result.strip().upper())
    if keyword is not None and keyword.strip():
        conditions.append(build_log_keyword_condition(keyword.strip()))
    groups = normalize_action_groups(action_group)
    if groups:
        conditions.append(SystemLog.action_group.in_(groups))
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

    items: list[AuditLogPayload] = []
    for item in rows:
        detail_json = coalesce_json(item.detail_json)
        items.append(
            AuditLogPayload(
                id=item.id,
                request_id=item.request_id or "",
                operator_user_id=item.operator_user_id,
                action=item.action or "",
                action_zh=resolve_action_zh(
                    action=item.action, action_zh=item.action_zh
                ),
                action_group=item.action_group or "",
                resource_type=item.resource_type or "",
                resource_id=item.resource_id or "",
                result=item.result or "",
                summary_zh=resolve_summary_zh(
                    action=item.action,
                    action_zh=item.action_zh,
                    summary_zh=item.summary_zh,
                    detail_json=detail_json,
                ),
                detail_json=detail_json,
                created_at=item.occurred_at,
            )
        )

    payload = AuditLogListPayload(items=items, total=total)
    return success_response(request, data=payload.model_dump())
