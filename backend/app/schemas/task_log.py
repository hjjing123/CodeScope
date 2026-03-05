from __future__ import annotations

import uuid

from pydantic import BaseModel


class TaskLogEntryPayload(BaseModel):
    stage: str
    lines: list[str]
    line_count: int
    truncated: bool


class TaskLogPayload(BaseModel):
    task_type: str
    task_id: uuid.UUID
    items: list[TaskLogEntryPayload]
