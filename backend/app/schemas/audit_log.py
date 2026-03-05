from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogPayload(BaseModel):
    id: uuid.UUID
    request_id: str
    operator_user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str
    project_id: uuid.UUID | None
    result: str
    error_code: str | None
    detail_json: dict[str, object]
    created_at: datetime


class AuditLogListPayload(BaseModel):
    items: list[AuditLogPayload]
    total: int
