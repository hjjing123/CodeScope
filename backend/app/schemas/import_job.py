from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GitImportRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=1024)
    ref_type: str | None = Field(default=None, max_length=16)
    ref_value: str | None = Field(default=None, max_length=255)
    repo_visibility: str | None = Field(default=None, max_length=16)
    auth_type: str | None = Field(default=None, max_length=32)
    username: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, max_length=4096)
    ssh_private_key: str | None = Field(default=None, max_length=20000)
    ssh_passphrase: str | None = Field(default=None, max_length=4096)
    credential_id: str | None = Field(default=None, max_length=255)
    version_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1024)


class GitImportTestRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=1024)
    ref_type: str | None = Field(default=None, max_length=16)
    ref_value: str | None = Field(default=None, max_length=255)
    repo_visibility: str | None = Field(default=None, max_length=16)
    auth_type: str | None = Field(default=None, max_length=32)
    username: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, max_length=4096)
    ssh_private_key: str | None = Field(default=None, max_length=20000)
    ssh_passphrase: str | None = Field(default=None, max_length=4096)
    credential_id: str | None = Field(default=None, max_length=255)


class ImportJobStageProgressPayload(BaseModel):
    stage: str
    display_name: str
    order: int
    status: str


class ImportJobProgressPayload(BaseModel):
    current_stage: str
    percent: int
    completed_stages: int
    total_stages: int
    is_terminal: bool = False
    stages: list[ImportJobStageProgressPayload] = Field(default_factory=list)


class ImportJobTriggerPayload(BaseModel):
    import_job_id: uuid.UUID
    idempotent_replay: bool = False


class ImportJobPayload(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version_id: uuid.UUID | None
    import_type: str
    payload: dict[str, object]
    status: str
    stage: str
    progress: ImportJobProgressPayload
    result_summary: dict[str, object] = Field(default_factory=dict)
    failure_code: str | None
    failure_hint: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class GitImportTestPayload(BaseModel):
    ok: bool
    resolved_ref: str
    resolved_ref_type: str
    resolved_ref_value: str
    auto_detected: bool = False
