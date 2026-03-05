from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.audit_log import AuditLogPayload
from app.schemas.runtime_log import RuntimeLogPayload


class TaskLogPreviewPayload(BaseModel):
    task_type: str
    task_id: str
    stage: str
    line_count: int
    size_bytes: int
    updated_at: datetime


class LogCenterCorrelationPayload(BaseModel):
    audit_logs: list[AuditLogPayload]
    runtime_logs: list[RuntimeLogPayload]
    task_log_previews: list[TaskLogPreviewPayload]
