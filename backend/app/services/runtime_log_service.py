from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal
from app.models import RuntimeLogLevel, RuntimeService, SystemLog, SystemLogKind


def append_runtime_log(
    *,
    level: str = RuntimeLogLevel.INFO.value,
    service: str = RuntimeService.API.value,
    module: str = "api",
    event: str,
    message: str,
    request_id: str = "",
    operator_user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    task_type: str | None = None,
    task_id: uuid.UUID | None = None,
    status_code: int | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    detail_json: dict[str, object] | None = None,
    db: Session | None = None,
) -> None:
    owns_db = True
    if db is None:
        session = SessionLocal()
    else:
        bind = db.get_bind()
        scoped = sessionmaker(
            bind=bind,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        session = scoped()
    try:
        session.add(
            SystemLog(
                log_kind=SystemLogKind.RUNTIME.value,
                level=level,
                service=service,
                module=module,
                event=event,
                message=message,
                request_id=request_id,
                operator_user_id=operator_user_id,
                project_id=project_id,
                resource_type=resource_type,
                resource_id=resource_id,
                task_type=task_type,
                task_id=task_id,
                status_code=status_code,
                duration_ms=duration_ms,
                error_code=error_code,
                detail_json=detail_json or {},
            )
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        if owns_db:
            session.close()


def build_request_runtime_detail(
    *,
    method: str,
    path: str,
    query: str,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, object]:
    return {
        "method": method,
        "path": path,
        "query": query,
        "client_ip": client_ip,
        "user_agent": user_agent,
    }


def normalize_level_for_status(status_code: int) -> str:
    if status_code >= 500:
        return RuntimeLogLevel.ERROR.value
    if status_code >= 400:
        return RuntimeLogLevel.WARN.value
    return RuntimeLogLevel.INFO.value


def infer_error_code_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    if not isinstance(code, str):
        return None
    normalized = code.strip().upper()
    return normalized or None
