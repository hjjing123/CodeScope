from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScanJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID = Field(description="项目 ID")
    version_id: uuid.UUID = Field(description="代码快照 ID")
    rule_set_keys: list[str] = Field(default_factory=list)
    rule_keys: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=1024)


class JobTriggerPayload(BaseModel):
    job_id: uuid.UUID
    idempotent_replay: bool = False


class JobStepPayload(BaseModel):
    step_key: str
    display_name: str
    step_order: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class JobProgressPayload(BaseModel):
    total_steps: int
    completed_steps: int
    percent: int
    current_step: str | None


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
    progress: JobProgressPayload
    steps: list[JobStepPayload]
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


class JobDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[str] = Field(default_factory=list)


class JobDeletePayload(BaseModel):
    ok: bool
    job_id: uuid.UUID
    deleted_targets: list[str]
    forced_targets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    deleted_findings_count: int = 0
    deleted_job_steps_count: int = 0
    deleted_task_log_index_count: int = 0
    deleted_log_files_count: int = 0
    deleted_archive_files_count: int = 0
    deleted_report_files_count: int = 0
    deleted_workspace_paths_count: int = 0
    deleted_job_record: bool = False


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
