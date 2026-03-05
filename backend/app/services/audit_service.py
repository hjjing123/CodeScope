from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import SystemLog, SystemLogKind


def append_audit_log(
    db: Session,
    *,
    request_id: str,
    operator_user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str,
    project_id: uuid.UUID | None = None,
    result: str = "SUCCEEDED",
    error_code: str | None = None,
    detail_json: dict[str, object] | None = None,
) -> None:
    db.add(
        SystemLog(
            log_kind=SystemLogKind.OPERATION.value,
            request_id=request_id,
            operator_user_id=operator_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            result=result,
            error_code=error_code,
            detail_json=detail_json or {},
        )
    )
