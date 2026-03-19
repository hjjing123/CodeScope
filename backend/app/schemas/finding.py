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
    vuln_display_name: str | None = None
    severity: str
    status: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    entry_display: str | None = None
    entry_kind: str | None = None
    has_path: bool = False
    path_length: int | None = None
    source_file: str | None = None
    source_line: int | None = None
    sink_file: str | None = None
    sink_line: int | None = None
    evidence_json: dict[str, object] = Field(default_factory=dict)
    ai_review: dict[str, object] = Field(default_factory=dict)
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


class ScanResultRowPayload(BaseModel):
    scan_job_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    version_id: uuid.UUID
    version_name: str
    job_status: str
    result_generated_at: datetime
    created_at: datetime
    finished_at: datetime | None = None
    created_by: uuid.UUID | None = None
    rule_count: int = 0
    total_findings: int = 0
    severity_dist: dict[str, int] = Field(default_factory=dict)
    ai_enabled: bool = False
    ai_latest_status: str | None = None


class ScanResultListPayload(BaseModel):
    items: list[ScanResultRowPayload]
    total: int


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


class FindingPathNodePayload(BaseModel):
    node_id: int
    labels: list[str]
    file: str | None = None
    line: int | None = None
    column: int | None = None
    func_name: str | None = None
    display_name: str | None = None
    symbol_name: str | None = None
    owner_method: str | None = None
    type_name: str | None = None
    node_kind: str | None = None
    code_snippet: str | None = None
    node_ref: str
    raw_props: dict[str, object] = Field(default_factory=dict)


class FindingPathStepPayload(BaseModel):
    step_id: int
    labels: list[str]
    file: str | None = None
    line: int | None = None
    column: int | None = None
    func_name: str | None = None
    display_name: str | None = None
    symbol_name: str | None = None
    owner_method: str | None = None
    type_name: str | None = None
    node_kind: str | None = None
    code_snippet: str | None = None
    node_ref: str


class FindingHighlightRangePayload(BaseModel):
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    text: str | None = None
    kind: str | None = None
    confidence: str | None = None


class FindingPathEdgePayload(BaseModel):
    edge_id: int
    edge_type: str
    from_node_id: int | None = None
    to_node_id: int | None = None
    from_step_id: int | None = None
    to_step_id: int | None = None
    from_node_ref: str | None = None
    to_node_ref: str | None = None
    label: str | None = None
    is_hidden: bool = False
    props_json: dict[str, object] = Field(default_factory=dict)


class FindingPathPayload(BaseModel):
    path_id: int
    path_length: int
    steps: list[FindingPathStepPayload]
    nodes: list[FindingPathNodePayload] = Field(default_factory=list)
    edges: list[FindingPathEdgePayload] = Field(default_factory=list)


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
    highlight_ranges: list[FindingHighlightRangePayload] = Field(default_factory=list)
    focus_range: FindingHighlightRangePayload | None = None
