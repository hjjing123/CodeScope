from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GitImportRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=1024)
    ref_type: str = Field(min_length=1, max_length=16)
    ref_value: str = Field(min_length=1, max_length=255)
    credential_id: str | None = Field(default=None, max_length=255)
    version_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1024)


class GitImportTestRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=1024)
    ref_type: str = Field(min_length=1, max_length=16)
    ref_value: str = Field(min_length=1, max_length=255)
    credential_id: str | None = Field(default=None, max_length=255)


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
    failure_code: str | None
    failure_hint: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class GitImportTestPayload(BaseModel):
    ok: bool
    resolved_ref: str
