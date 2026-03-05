from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class RuntimeLogPayload(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    level: str
    service: str
    module: str
    event: str
    message: str
    request_id: str
    operator_user_id: uuid.UUID | None
    project_id: uuid.UUID | None
    resource_type: str | None
    resource_id: str | None
    task_type: str | None
    task_id: uuid.UUID | None
    status_code: int | None
    duration_ms: int | None
    error_code: str | None
    detail_json: dict[str, object]
    created_at: datetime


class RuntimeLogListPayload(BaseModel):
    items: list[RuntimeLogPayload]
    total: int
