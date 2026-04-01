from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import SystemLog, SystemLogKind
from app.services.auth_service import AuthPrincipal
from app.services.log_center_service import (
    build_log_keyword_condition,
    normalize_action_groups,
)


router = APIRouter(tags=["log-center"])


class BatchDeleteLogsRequest(BaseModel):
    log_kind: str | None = None
    request_id: str | None = None
    task_type: str | None = None
    task_id: uuid.UUID | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    keyword: str | None = None
    action_group: str | None = None


def _build_delete_conditions(
    *,
    log_kind: str | None,
    request_id: str | None,
    task_type: str | None,
    task_id: uuid.UUID | None,
    start_time: datetime | None,
    end_time: datetime | None,
    keyword: str | None,
    action_group: str | None,
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
    if start_time is not None:
        conditions.append(SystemLog.occurred_at >= start_time)
    if end_time is not None:
        conditions.append(SystemLog.occurred_at <= end_time)
    if keyword is not None and keyword.strip():
        conditions.append(build_log_keyword_condition(keyword.strip()))
    groups = normalize_action_groups(action_group)
    if groups:
        conditions.append(SystemLog.action_group.in_(groups))
    return conditions


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
        start_time=payload.start_time,
        end_time=payload.end_time,
        keyword=payload.keyword,
        action_group=payload.action_group,
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
