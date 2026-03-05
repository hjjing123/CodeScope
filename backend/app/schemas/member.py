from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectMemberCreateRequest(BaseModel):
    user_id: uuid.UUID
    project_role: str


class ProjectMemberUpdateRequest(BaseModel):
    project_role: str


class ProjectMemberPayload(BaseModel):
    user_id: uuid.UUID
    project_id: uuid.UUID
    project_role: str
    granted_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectMemberListPayload(BaseModel):
    items: list[ProjectMemberPayload]
    total: int
