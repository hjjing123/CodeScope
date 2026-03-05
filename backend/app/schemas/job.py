from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ScanJobCreateRequest(BaseModel):
    project_id: uuid.UUID
    version_id: uuid.UUID
    scan_mode: str = Field(default="FULL", min_length=1, max_length=16)
    rule_set_ids: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=1024)
    target_rule_id: str | None = Field(default=None, max_length=128)


class JobTriggerPayload(BaseModel):
    job_id: uuid.UUID
    idempotent_replay: bool = False


class JobPayload(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version_id: uuid.UUID
    job_type: str
    payload: dict[str, object]
    status: str
    stage: str
    failure_code: str | None
    failure_stage: str | None
    failure_category: str | None
    failure_hint: str | None
    result_summary: dict[str, object]
    created_by: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobListPayload(BaseModel):
    items: list[JobPayload]
    total: int


class JobActionPayload(BaseModel):
    ok: bool
    job_id: uuid.UUID
    status: str


class JobLogEntryPayload(BaseModel):
    stage: str
    lines: list[str]
    line_count: int
    truncated: bool


class JobLogPayload(BaseModel):
    job_id: uuid.UUID
    items: list[JobLogEntryPayload]


class JobArtifactPayload(BaseModel):
    artifact_id: str
    artifact_type: str
    display_name: str
    size_bytes: int | None = None
    source: str


class JobArtifactListPayload(BaseModel):
    job_id: uuid.UUID
    items: list[JobArtifactPayload]
