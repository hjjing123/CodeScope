from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FindingPayload(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version_id: uuid.UUID
    job_id: uuid.UUID
    rule_key: str
    rule_version: int | None = None
    vuln_type: str | None = None
    severity: str
    status: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    has_path: bool = False
    path_length: int | None = None
    source_file: str | None = None
    source_line: int | None = None
    sink_file: str | None = None
    sink_line: int | None = None
    evidence_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class FindingListPayload(BaseModel):
    items: list[FindingPayload]
    total: int


class ProjectResultOverviewPayload(BaseModel):
    project_id: uuid.UUID
    version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    total_findings: int
    severity_dist: dict[str, int]
    status_dist: dict[str, int]
    top_vuln_types: list[dict[str, object]]


class FindingLabelRequest(BaseModel):
    status: str = Field(min_length=1, max_length=16)
    fp_reason: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1024)


class FindingLabelPayload(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    status: str
    fp_reason: str | None = None
    comment: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class FindingLabelActionPayload(BaseModel):
    finding: FindingPayload
    label: FindingLabelPayload


class FindingPathStepPayload(BaseModel):
    step_id: int
    labels: list[str]
    file: str | None = None
    line: int | None = None
    func_name: str | None = None
    code_snippet: str | None = None
    node_ref: str


class FindingPathPayload(BaseModel):
    path_id: int
    path_length: int
    steps: list[FindingPathStepPayload]


class FindingPathListPayload(BaseModel):
    finding_id: uuid.UUID
    mode: str
    items: list[FindingPathPayload]


class FindingPathNodeContextPayload(BaseModel):
    finding_id: uuid.UUID
    step_id: int
    file: str
    line: int
    start_line: int
    end_line: int
    lines: list[str]
