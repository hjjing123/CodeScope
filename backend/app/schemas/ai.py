from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AIProviderSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_source: str | None = Field(default=None, max_length=64)
    ai_provider_id: uuid.UUID | None = None
    ai_model: str | None = Field(default=None, max_length=255)


class SystemOllamaConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(default="System Ollama", min_length=1, max_length=255)
    base_url: str = Field(min_length=1, max_length=1024)
    enabled: bool = True
    default_model: str | None = Field(default=None, max_length=255)
    published_models: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class SystemOllamaConfigPayload(BaseModel):
    id: uuid.UUID | None = None
    provider_key: str
    display_name: str
    provider_type: str
    base_url: str
    enabled: bool
    default_model: str | None = None
    published_models: list[str] = Field(default_factory=list)
    timeout_seconds: int
    temperature: float
    is_configured: bool
    auto_configured: bool = False
    connection_ok: bool | None = None
    connection_detail: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OllamaModelPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)


class OllamaModelPayload(BaseModel):
    name: str
    size: int | None = None
    digest: str | None = None
    modified_at: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class OllamaModelListPayload(BaseModel):
    items: list[OllamaModelPayload]


class SystemOllamaPullJobProgressPayload(BaseModel):
    phase: str | None = None
    status_text: str | None = None
    percent: int = 0
    completed: int | None = None
    total: int | None = None
    digest: str | None = None
    verified: bool = False


class SystemOllamaPullJobPayload(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    model_name: str
    status: str
    stage: str
    failure_code: str | None = None
    failure_hint: str | None = None
    progress: SystemOllamaPullJobProgressPayload
    result_summary: dict[str, object] = Field(default_factory=dict)
    created_by: uuid.UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SystemOllamaPullJobListPayload(BaseModel):
    items: list[SystemOllamaPullJobPayload]
    total: int


class SystemOllamaPullJobTriggerPayload(BaseModel):
    ok: bool = True
    pull_job_id: uuid.UUID
    idempotent_replay: bool = False
    already_present: bool = False
    job: SystemOllamaPullJobPayload


class AIProviderTestPayload(BaseModel):
    ok: bool
    provider_type: str
    provider_label: str
    detail: dict[str, object] = Field(default_factory=dict)


class UserAIProviderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    vendor_name: str = Field(default="OpenAI Compatible", min_length=1, max_length=255)
    base_url: str = Field(min_length=1, max_length=1024)
    api_key: str = Field(min_length=1, max_length=4096)
    default_model: str = Field(min_length=1, max_length=255)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    enabled: bool = True
    is_default: bool = False


class UserAIProviderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    vendor_name: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, min_length=1, max_length=1024)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    default_model: str | None = Field(default=None, min_length=1, max_length=255)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    enabled: bool | None = None
    is_default: bool | None = None


class UserAIProviderPayload(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    vendor_name: str
    provider_type: str
    base_url: str
    default_model: str
    timeout_seconds: int
    temperature: float
    enabled: bool
    is_default: bool
    has_api_key: bool
    api_key_masked: str | None = None
    created_at: datetime
    updated_at: datetime


class UserAIProviderListPayload(BaseModel):
    items: list[UserAIProviderPayload]
    total: int


class SystemAIOptionPayload(BaseModel):
    available: bool
    provider_key: str = "system_ollama"
    display_name: str = "System Ollama"
    provider_type: str = "ollama_local"
    default_model: str | None = None
    published_models: list[str] = Field(default_factory=list)
    connection_ok: bool | None = None


class AIProviderOptionsPayload(BaseModel):
    system_ollama: SystemAIOptionPayload
    user_providers: list[UserAIProviderPayload] = Field(default_factory=list)
    default_selection: dict[str, object] = Field(default_factory=dict)


class AISelectableModelPayload(BaseModel):
    name: str
    label: str
    is_default: bool = False
    selectable: bool = True
    details: dict[str, object] = Field(default_factory=dict)


class AIModelCatalogProviderPayload(BaseModel):
    provider_source: str
    provider_id: uuid.UUID | None = None
    provider_key: str | None = None
    provider_label: str
    provider_type: str
    enabled: bool
    default_model: str | None = None
    available: bool = False
    connection_ok: bool | None = None
    model_catalog_ok: bool | None = None
    allow_manual_model_input: bool = False
    source_label: str | None = None
    status_label: str | None = None
    status_reason: str | None = None
    models: list[AISelectableModelPayload] = Field(default_factory=list)


class AIModelCatalogPayload(BaseModel):
    items: list[AIModelCatalogProviderPayload] = Field(default_factory=list)
    default_selection: dict[str, object] = Field(default_factory=dict)


class FindingAIAssessmentPayload(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    job_id: uuid.UUID
    scan_job_id: uuid.UUID | None = None
    project_id: uuid.UUID
    version_id: uuid.UUID
    provider_source: str
    provider_type: str
    provider_label: str
    model_name: str
    status: str
    summary_json: dict[str, object] = Field(default_factory=dict)
    request_messages_json: list[dict[str, object]] = Field(default_factory=list)
    context_snapshot_json: dict[str, object] = Field(default_factory=dict)
    response_text: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class FindingAIAssessmentListPayload(BaseModel):
    items: list[FindingAIAssessmentPayload]
    total: int


class AIChatSessionCreateRequest(AIProviderSelectionRequest):
    title: str | None = Field(default=None, max_length=255)


class AIChatSessionSelectionUpdateRequest(AIProviderSelectionRequest):
    model_config = ConfigDict(extra="forbid")


class AIChatMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20_000)


class AIChatMessagePayload(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    meta_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class AIChatSessionPayload(BaseModel):
    id: uuid.UUID
    session_mode: str
    finding_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    provider_source: str
    provider_type: str
    provider_label: str
    model_name: str
    title: str | None = None
    provider_snapshot: dict[str, object] = Field(default_factory=dict)
    seed_kind: str | None = None
    seed_assessment_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[AIChatMessagePayload] = Field(default_factory=list)


class AIChatSessionDeletePayload(BaseModel):
    ok: bool = True
    session_id: uuid.UUID


class FindingAIAssessmentContextPayload(BaseModel):
    assessment_id: uuid.UUID
    finding_id: uuid.UUID
    request_messages: list[dict[str, object]] = Field(default_factory=list)
    context_snapshot: dict[str, object] = Field(default_factory=dict)
    response_text: str | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class AIAssessmentChatSessionTriggerPayload(BaseModel):
    ok: bool = True
    session_id: uuid.UUID
    assessment_id: uuid.UUID
    idempotent_replay: bool = False


class AIChatSessionListPayload(BaseModel):
    items: list[AIChatSessionPayload]
    total: int


class AIEnrichmentJobPayload(BaseModel):
    scan_job_id: uuid.UUID
    enabled: bool
    latest_job_id: uuid.UUID | None = None
    latest_status: str | None = None
    jobs: list[dict[str, object]] = Field(default_factory=list)
