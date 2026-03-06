from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import SystemLog, SystemLogKind
from app.services.log_center_service import (
    build_audit_summary_zh,
    normalize_audit_detail,
    resolve_audit_action_meta,
)


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
    normalized_detail = normalize_audit_detail(action=action, detail_json=detail_json)
    action_meta = resolve_audit_action_meta(action)
    db.add(
        SystemLog(
            log_kind=SystemLogKind.OPERATION.value,
            request_id=request_id,
            operator_user_id=operator_user_id,
            action=action,
            action_zh=action_meta.action_zh,
            action_group=action_meta.action_group,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            result=result,
            error_code=error_code,
            summary_zh=build_audit_summary_zh(action=action, detail_json=normalized_detail),
            is_high_value=action_meta.is_high_value,
            detail_json=normalized_detail,
        )
    )
