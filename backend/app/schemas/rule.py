from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class RuleCreateRequest(BaseModel):
    rule_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    vuln_type: str = Field(min_length=1, max_length=64)
    default_severity: str = Field(default="MED", min_length=1, max_length=16)
    language_scope: str = Field(default="java", min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=1024)
    content: dict = Field(default_factory=dict)


class RuleDraftUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    vuln_type: str | None = Field(default=None, min_length=1, max_length=64)
    default_severity: str | None = Field(default=None, min_length=1, max_length=16)
    language_scope: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=1024)
    content: dict | None = None


class RuleRollbackRequest(BaseModel):
    version: int = Field(ge=1)


class RuleToggleRequest(BaseModel):
    enabled: bool


class RulePayload(BaseModel):
    rule_key: str
    name: str
    vuln_type: str
    default_severity: str
    language_scope: str
    description: str | None
    enabled: bool
    active_version: int | None
    created_at: datetime
    updated_at: datetime


class RuleVersionPayload(BaseModel):
    id: uuid.UUID
    rule_key: str
    version: int
    status: str
    content: dict
    created_by: uuid.UUID | None
    created_at: datetime


class RuleVersionListPayload(BaseModel):
    items: list[RuleVersionPayload]
    total: int


class RuleListPayload(BaseModel):
    items: list[RulePayload]
    total: int


class RuleSetCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    enabled: bool = True


class RuleSetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    enabled: bool | None = None


class RuleSetBindRulesRequest(BaseModel):
    rule_keys: list[str] = Field(min_length=1, max_length=1000)


class RuleSetPayload(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    enabled: bool
    rule_count: int
    created_at: datetime
    updated_at: datetime


class RuleSetListPayload(BaseModel):
    items: list[RuleSetPayload]
    total: int


class RuleSetItemPayload(BaseModel):
    id: uuid.UUID
    rule_set_id: uuid.UUID
    rule_key: str
    created_at: datetime


class RuleSetDetailPayload(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    enabled: bool
    items: list[RuleSetItemPayload]
    created_at: datetime
    updated_at: datetime


class RuleStatPayload(BaseModel):
    rule_key: str
    rule_version: int
    metric_date: date
    hits: int
    avg_duration_ms: int
    timeout_count: int
    fp_count: int


class RuleStatListPayload(BaseModel):
    items: list[RuleStatPayload]
    total: int


class RuleSelfTestCreateRequest(BaseModel):
    rule_key: str | None = Field(default=None, min_length=1, max_length=128)
    rule_version: int | None = Field(default=None, ge=1)
    draft_payload: dict | None = None
    version_id: uuid.UUID | None = None


class RuleSelfTestTriggerPayload(BaseModel):
    selftest_job_id: uuid.UUID


class RuleSelfTestPayload(BaseModel):
    id: uuid.UUID
    rule_key: str | None
    rule_version: int | None
    payload: dict[str, object]
    status: str
    stage: str
    failure_code: str | None
    failure_hint: str | None
    result_summary: dict[str, object]
    created_by: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
