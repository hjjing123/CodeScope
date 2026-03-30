from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportJobCreateOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["MARKDOWN"] = "MARKDOWN"
    include_code_snippets: bool = True
    include_ai_sections: bool = True


class ReportJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: Literal["FINDING"] = "FINDING"
    generation_mode: Literal["JOB_ALL", "FINDING_SET"]
    project_id: uuid.UUID
    version_id: uuid.UUID
    job_id: uuid.UUID
    finding_ids: list[uuid.UUID] = Field(default_factory=list)
    options: ReportJobCreateOptions = Field(default_factory=ReportJobCreateOptions)


class ReportJobTriggerPayload(BaseModel):
    report_job_id: uuid.UUID
    expected_report_count: int
    bundle_expected: bool


class ReportPayload(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    report_job_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    report_type: str
    status: str
    format: str
    object_key: str | None = None
    file_name: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    rule_key: str | None = None
    vuln_type: str | None = None
    vuln_display_name: str | None = None
    severity: str | None = None
    finding_status: str | None = None
    entry_display: str | None = None
    entry_kind: str | None = None


class ReportListPayload(BaseModel):
    items: list[ReportPayload]
    total: int
