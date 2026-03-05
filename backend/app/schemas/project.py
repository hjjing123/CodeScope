from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=1024)


class ProjectPayload(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    baseline_version_id: uuid.UUID | None
    my_project_role: str | None
    created_at: datetime
    updated_at: datetime


class ProjectListPayload(BaseModel):
    items: list[ProjectPayload]
    total: int
