from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import SystemLog, SystemLogKind, TaskLogIndex, TaskLogType
from app.schemas.audit_log import AuditLogPayload
from app.schemas.log_center import LogCenterCorrelationPayload, TaskLogPreviewPayload
from app.services.auth_service import AuthPrincipal
from app.services.log_center_service import (
    build_log_keyword_condition,
    coalesce_json,
    normalize_action_groups,
    resolve_action_zh,
    to_int_or_none,
)
from app.services.task_log_service import sync_task_log_index


router = APIRouter(tags=["log-center"])


class BatchDeleteLogsRequest(BaseModel):
    log_kind: str | None = None
    request_id: str | None = None
    task_type: str | None = None
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    keyword: str | None = None
    action_group: str | None = None
    high_value_only: bool = False


def _audit_payload(item: SystemLog) -> AuditLogPayload:
    return AuditLogPayload(
        id=item.id,
        request_id=item.request_id or "",
        operator_user_id=item.operator_user_id,
        action=item.action or "",
        action_zh=resolve_action_zh(action=item.action, action_zh=item.action_zh),
        action_group=item.action_group or "",
        resource_type=item.resource_type or "",
        resource_id=item.resource_id or "",
        project_id=item.project_id,
        result=item.result or "",
        error_code=item.error_code,
        summary_zh=item.summary_zh or "",
        is_high_value=bool(item.is_high_value),
        detail_json=coalesce_json(item.detail_json),
        created_at=item.occurred_at,
    )


def _build_delete_conditions(
    *,
    log_kind: str | None,
    request_id: str | None,
    task_type: str | None,
    task_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    start_time: datetime | None,
    end_time: datetime | None,
    keyword: str | None,
    action_group: str | None,
    high_value_only: bool,
) -> list[object]:
    conditions: list[object] = []
    normalized_kind = (log_kind or "").strip().upper()
    if normalized_kind:
        if normalized_kind not in {item.value for item in SystemLogKind}:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="log_kind 参数不合法",
                detail={"allowed_log_kinds": [item.value for item in SystemLogKind]},
            )
        conditions.append(SystemLog.log_kind == normalized_kind)
    if request_id is not None and request_id.strip():
        conditions.append(SystemLog.request_id == request_id.strip())
    if task_type is not None and task_type.strip():
        conditions.append(SystemLog.task_type == task_type.strip().upper())
    if task_id is not None:
        conditions.append(SystemLog.task_id == task_id)
    if project_id is not None:
        conditions.append(SystemLog.project_id == project_id)
    if start_time is not None:
        conditions.append(SystemLog.occurred_at >= start_time)
    if end_time is not None:
        conditions.append(SystemLog.occurred_at <= end_time)
    if keyword is not None and keyword.strip():
        conditions.append(build_log_keyword_condition(keyword.strip()))
    groups = normalize_action_groups(action_group)
    if groups:
        conditions.append(SystemLog.action_group.in_(groups))
    if high_value_only:
        conditions.append(SystemLog.is_high_value.is_(True))
    return conditions


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
    task_conditions = []

    if normalized_request_id:
        audit_conditions.append(SystemLog.request_id == normalized_request_id)
    if project_id is not None:
        audit_conditions.append(SystemLog.project_id == project_id)
        task_conditions.append(TaskLogIndex.project_id == project_id)
    if task_id is not None:
        task_conditions.append(TaskLogIndex.task_id == task_id)
    if normalized_task_type:
        task_conditions.append(TaskLogIndex.task_type == normalized_task_type)
    if start_time is not None:
        audit_conditions.append(SystemLog.occurred_at >= start_time)
        task_conditions.append(TaskLogIndex.updated_at >= start_time)
    if end_time is not None:
        audit_conditions.append(SystemLog.occurred_at <= end_time)
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

    task_stmt = select(TaskLogIndex)
    if task_conditions:
        task_stmt = task_stmt.where(*task_conditions)
    task_rows = db.scalars(
        task_stmt.order_by(TaskLogIndex.updated_at.desc()).limit(limit)
    ).all()

    payload = LogCenterCorrelationPayload(
        audit_logs=[_audit_payload(item) for item in audit_rows],
        task_log_previews=[
            TaskLogPreviewPayload(
                task_type=item.task_type or "",
                task_id=str(item.task_id) if item.task_id is not None else "",
                stage=item.stage or "",
                line_count=to_int_or_none(item.line_count) or 0,
                size_bytes=to_int_or_none(item.size_bytes) or 0,
                updated_at=item.updated_at,
            )
            for item in task_rows
        ],
    )
    return success_response(request, data=payload.model_dump())


@router.delete("/api/v1/log-center/logs/{log_id}")
def delete_single_log(
    request: Request,
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:auditlog")),
):
    target = db.get(SystemLog, log_id)
    if target is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="日志不存在")
    db.delete(target)
    db.commit()
    return success_response(request, data={"deleted": True, "deleted_count": 1})


@router.post("/api/v1/log-center/logs/batch-delete")
def batch_delete_logs(
    request: Request,
    payload: BatchDeleteLogsRequest,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:auditlog")),
):
    conditions = _build_delete_conditions(
        log_kind=payload.log_kind,
        request_id=payload.request_id,
        task_type=payload.task_type,
        task_id=payload.task_id,
        project_id=payload.project_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        keyword=payload.keyword,
        action_group=payload.action_group,
        high_value_only=payload.high_value_only,
    )
    if not conditions:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="批量删除必须至少提供一个筛选条件",
        )

    rows_stmt = select(SystemLog.id).where(*conditions)
    rows = db.execute(rows_stmt).all()
    target_ids = [row.id for row in rows]
    if not target_ids:
        return success_response(request, data={"deleted_count": 0})
    db.execute(delete(SystemLog).where(SystemLog.id.in_(target_ids)))
    db.commit()
    return success_response(request, data={"deleted_count": len(target_ids)})
