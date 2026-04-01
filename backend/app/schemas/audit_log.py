from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogPayload(BaseModel):
    id: uuid.UUID
    request_id: str
    operator_user_id: uuid.UUID | None
    action: str
    action_zh: str
    action_group: str
    resource_type: str
    resource_id: str
    result: str
    summary_zh: str
    detail_json: dict[str, object]
    created_at: datetime


class AuditLogListPayload(BaseModel):
    items: list[AuditLogPayload]
    total: int
