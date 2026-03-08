from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VersionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source: str = Field(default="UPLOAD")
    note: str | None = Field(default=None, max_length=1024)
    tag: str | None = Field(default=None, max_length=64)
    git_repo_url: str | None = Field(default=None, max_length=1024)
    git_ref: str | None = Field(default=None, max_length=255)
    snapshot_object_key: str | None = Field(default=None, max_length=255)


class VersionPayload(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    source: str
    note: str | None
    tag: str | None
    git_repo_url: str | None
    git_ref: str | None
    snapshot_object_key: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class VersionListPayload(BaseModel):
    items: list[VersionPayload]
    total: int


class VersionTreeEntryPayload(BaseModel):
    name: str
    path: str
    node_type: str
    size_bytes: int | None


class VersionTreePayload(BaseModel):
    root_path: str
    items: list[VersionTreeEntryPayload]


class VersionFilePayload(BaseModel):
    path: str
    content: str
    truncated: bool
    total_lines: int
