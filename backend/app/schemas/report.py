from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportJobCreateOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["MARKDOWN"] = "MARKDOWN"
    include_code_snippets: bool = True
    include_ai_sections: bool = True


class ReportJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: Literal["SCAN", "FINDING"]
    project_id: uuid.UUID
    version_id: uuid.UUID
    job_id: uuid.UUID
    finding_id: uuid.UUID | None = None
    options: ReportJobCreateOptions = Field(default_factory=ReportJobCreateOptions)

    @model_validator(mode="after")
    def validate_scope(self) -> "ReportJobCreateRequest":
        if self.report_type == "FINDING" and self.finding_id is None:
            raise ValueError("FINDING 报告必须提供 finding_id")
        if self.report_type == "SCAN" and self.finding_id is not None:
            raise ValueError("SCAN 报告不应提供 finding_id")
        return self


class ReportJobTriggerPayload(BaseModel):
    report_job_id: uuid.UUID
    report_type: Literal["SCAN", "FINDING"]
    finding_count: int


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
    title: str | None = None
    template_key: str | None = None
    summary_text: str | None = None
    finding_count: int | None = None
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


class ReportContentPayload(BaseModel):
    report: ReportPayload
    content: str
    mime_type: Literal["text/markdown"] = "text/markdown"


class ReportDeletePayload(BaseModel):
    ok: bool
    report_id: uuid.UUID
    report_job_id: uuid.UUID | None = None
    remaining_report_count: int = 0
    deleted_report_file: bool = False
    deleted_report_job_root: bool = False
    deleted_report_job_files_count: int = 0
    deleted_task_log_index_count: int = 0
    deleted_log_files_count: int = 0
