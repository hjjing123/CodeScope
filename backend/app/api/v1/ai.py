from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden_error
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_principal,
    require_platform_action,
    require_project_resource_action,
)
from app.models import AIAssessmentStatus, Finding, Job
from app.schemas.ai import (
    AIAssessmentChatSessionTriggerPayload,
    AIChatSessionDeletePayload,
    AIChatSessionSelectionUpdateRequest,
    AIChatMessageCreateRequest,
    AIChatMessagePayload,
    AIChatSessionCreateRequest,
    FindingAIAssessmentContextPayload,
    AIChatSessionListPayload,
    AIChatSessionPayload,
    AIEnrichmentJobPayload,
    AIModelCatalogPayload,
    AIProviderOptionsPayload,
    AIProviderSelectionRequest,
    AIProviderDraftTestPayload,
    AIProviderDraftTestRequest,
    AIProviderTestPayload,
    FindingAIAssessmentListPayload,
    FindingAIAssessmentPayload,
    OllamaModelListPayload,
    OllamaModelPayload,
    OllamaModelPullRequest,
    SystemOllamaPullJobListPayload,
    SystemOllamaPullJobPayload,
    SystemOllamaPullJobTriggerPayload,
    SystemOllamaConfigPayload,
    SystemOllamaConfigRequest,
    UserAIProviderCreateRequest,
    UserAIProviderListPayload,
    UserAIProviderPayload,
    UserAIProviderUpdateRequest,
)
from app.schemas.job import JobTriggerPayload
from app.schemas.task_log import TaskLogEntryPayload, TaskLogPayload
from app.services.ai_service import (
    build_ai_job_summary,
    build_ai_model_catalog_payload,
    build_chat_message_payload,
    build_chat_session_payload,
    build_ai_provider_options_payload,
    build_finding_ai_assessment_payload,
    build_system_ollama_payload,
    build_user_ai_provider_payload,
    create_assessment_seed_chat_session,
    create_general_chat_session,
    create_chat_session,
    create_finding_retry_ai_job,
    create_chat_assistant_message,
    create_chat_user_message,
    create_user_ai_provider,
    probe_user_ai_provider_draft,
    delete_chat_session,
    delete_system_ollama_model_by_name,
    delete_user_ai_provider,
    dispatch_ai_job,
    ensure_system_ollama_provider,
    get_chat_session,
    get_latest_finding_ai_assessment,
    get_ollama_model_payloads,
    get_user_ai_provider,
    list_chat_messages,
    list_chat_sessions,
    list_finding_ai_assessments,
    list_scan_related_ai_jobs,
    list_user_chat_sessions,
    list_user_ai_providers,
    mark_ai_dispatch_failed,
    prepare_chat_completion_request,
    resolve_provider_snapshot,
    send_chat_message,
    test_system_ollama_provider,
    test_user_ai_provider,
    update_chat_session_selection,
    update_user_ai_provider,
    upsert_system_ollama_provider,
)
from app.services.ai_client_service import iter_provider_chat_stream
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.authorization_service import ensure_resource_action
from app.services.system_ollama_pull_service import (
    ACTIVE_PULL_STATUSES,
    build_system_ollama_pull_payload,
    dispatch_system_ollama_pull_job,
    get_system_ollama_pull_job,
    list_system_ollama_pull_jobs,
    mark_system_ollama_pull_dispatch_failed,
    trigger_system_ollama_pull_job,
)
from app.services.task_log_service import (
    read_task_log_events,
    read_task_logs,
    sync_task_log_index,
)


router = APIRouter(tags=["ai"])


def _encode_sse_event(
    *,
    event: str,
    data: dict[str, object],
    event_id: int | None = None,
) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for chunk in payload.splitlines() or ["{}"]:
        lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


def _ensure_chat_session_access(
    *, db: Session, principal: AuthPrincipal, session_id: uuid.UUID
):
    session = get_chat_session(db, session_id=session_id)
    if session.finding_id is not None:
        ensure_resource_action(
            db=db,
            user_id=principal.user.id,
            role=principal.user.role,
            action="finding:read",
            resource_type="FINDING",
            resource_id=session.finding_id,
        )
        return session

    if session.created_by != principal.user.id:
        raise forbidden_error(message="无权限访问该 AI 会话")
    return session


def _ensure_chat_session_owner_access(
    *, db: Session, principal: AuthPrincipal, session_id: uuid.UUID
):
    session = get_chat_session(db, session_id=session_id)
    if session.created_by != principal.user.id:
        raise forbidden_error(message="仅创建者可以删除该 AI 会话")
    return session


@router.get("/api/v1/system/ai/ollama")
def get_system_ollama_config(
    request: Request,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    provider, probe_result = ensure_system_ollama_provider(db, probe=True)
    db.commit()
    payload = SystemOllamaConfigPayload(
        **build_system_ollama_payload(
            provider,
            auto_configured=bool(probe_result.get("auto_configured")),
            connection_ok=probe_result.get("connection_ok"),
            connection_detail=probe_result.get("connection_detail") or {},
        )
    )
    return success_response(request, data=payload.model_dump())


@router.patch("/api/v1/system/ai/ollama")
def update_system_ollama_config(
    request: Request,
    payload: SystemOllamaConfigRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    provider = upsert_system_ollama_provider(
        db,
        display_name=payload.display_name,
        base_url=payload.base_url,
        enabled=payload.enabled,
        default_model=payload.default_model,
        published_models=payload.published_models,
        timeout_seconds=payload.timeout_seconds,
        temperature=payload.temperature,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="system.ai.ollama.updated",
        resource_type="SYSTEM_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json={
            "base_url": provider.base_url,
            "enabled": provider.enabled,
            "default_model": provider.default_model,
            "published_model_count": len(provider.published_models_json),
        },
    )
    db.commit()
    db.refresh(provider)
    data = SystemOllamaConfigPayload(**build_system_ollama_payload(provider))
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/system/ai/ollama/test")
def test_system_ollama(
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    provider, _probe_result = ensure_system_ollama_provider(db, probe=False)
    if provider is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="系统 Ollama 未配置")
    result = AIProviderTestPayload(**test_system_ollama_provider(provider))
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="system.ai.ollama.tested",
        resource_type="SYSTEM_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json=result.detail,
    )
    db.commit()
    return success_response(request, data=result.model_dump())


@router.get("/api/v1/system/ai/ollama/models")
def list_ollama_models_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    provider, _probe_result = ensure_system_ollama_provider(db, probe=False)
    if provider is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="系统 Ollama 未配置")
    items = [OllamaModelPayload(**item) for item in get_ollama_model_payloads(provider)]
    data = OllamaModelListPayload(items=items)
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/system/ai/ollama/pull")
def pull_ollama_model_endpoint(
    request: Request,
    payload: OllamaModelPullRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    provider, _probe_result = ensure_system_ollama_provider(db, probe=False)
    if provider is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="系统 Ollama 未配置")
    pull_job, idempotent_replay, already_present = trigger_system_ollama_pull_job(
        db,
        provider=provider,
        name=payload.name,
        created_by=principal.user.id,
        request_id=get_request_id(request),
    )
    if not idempotent_replay and not already_present:
        try:
            dispatch_system_ollama_pull_job(db, job=pull_job)
        except AppError:
            mark_system_ollama_pull_dispatch_failed(
                db,
                pull_job_id=pull_job.id,
                request_id=get_request_id(request),
                operator_user_id=principal.user.id,
            )
            raise
    db.refresh(pull_job)
    result = SystemOllamaPullJobPayload(
        **build_system_ollama_pull_payload(pull_job)
    ).model_dump()
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="system.ai.ollama.model.pull.triggered",
        resource_type="SYSTEM_OLLAMA_PULL_JOB",
        resource_id=str(pull_job.id),
        detail_json={
            "model": payload.name,
            "idempotent_replay": idempotent_replay,
            "already_present": already_present,
        },
    )
    db.commit()
    data = SystemOllamaPullJobTriggerPayload(
        ok=True,
        pull_job_id=pull_job.id,
        idempotent_replay=idempotent_replay,
        already_present=already_present,
        job=SystemOllamaPullJobPayload(**result),
    )
    return success_response(
        request,
        data=data.model_dump(),
        status_code=200 if idempotent_replay or already_present else 202,
    )


@router.get("/api/v1/system/ai/ollama/pull-jobs")
def list_ollama_pull_jobs_endpoint(
    request: Request,
    active_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    items = [
        SystemOllamaPullJobPayload(**build_system_ollama_pull_payload(item))
        for item in list_system_ollama_pull_jobs(
            db, active_only=active_only, limit=limit
        )
    ]
    data = SystemOllamaPullJobListPayload(items=items, total=len(items))
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/system/ai/ollama/pull-jobs/{pull_job_id}")
def get_ollama_pull_job_endpoint(
    request: Request,
    pull_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    job = get_system_ollama_pull_job(db, pull_job_id=pull_job_id)
    data = SystemOllamaPullJobPayload(**build_system_ollama_pull_payload(job))
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/system/ai/ollama/pull-jobs/{pull_job_id}/logs")
def get_ollama_pull_job_logs(
    request: Request,
    pull_job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    tail: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    job = get_system_ollama_pull_job(db, pull_job_id=pull_job_id)
    sync_task_log_index(
        task_type="OLLAMA_PULL",
        task_id=job.id,
        project_id=None,
        db=db,
    )
    items = read_task_logs(
        task_type="OLLAMA_PULL",
        task_id=job.id,
        stage=stage,
        tail=tail,
    )
    payload = TaskLogPayload(
        task_type="OLLAMA_PULL",
        task_id=job.id,
        items=[TaskLogEntryPayload(**item) for item in items],
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/system/ai/ollama/pull-jobs/{pull_job_id}/logs/stream")
def stream_ollama_pull_job_logs(
    request: Request,
    pull_job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    seq: int = Query(default=0, ge=0),
    poll_interval_ms: int = Query(default=500, ge=100, le=5000),
    max_wait_seconds: int = Query(default=30, ge=1, le=300),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    job = get_system_ollama_pull_job(db, pull_job_id=pull_job_id)

    def stream():
        current_seq = seq
        started_at = time.monotonic()
        while True:
            sync_task_log_index(
                task_type="OLLAMA_PULL",
                task_id=job.id,
                project_id=None,
                db=db,
            )
            events = read_task_log_events(
                task_type="OLLAMA_PULL",
                task_id=job.id,
                stage=stage,
                after_seq=current_seq,
                limit=2000,
            )
            for event in events:
                current_seq = int(event["seq"])
                yield _encode_sse_event(
                    event="log",
                    data=event,
                    event_id=current_seq,
                )

            db.expire_all()
            latest_job = db.get(type(job), job.id)
            if latest_job is None:
                break
            if latest_job.status not in ACTIVE_PULL_STATUSES:
                done_payload = {
                    "seq": current_seq,
                    "pull_job_id": str(job.id),
                    "status": latest_job.status,
                    "stage": latest_job.stage,
                }
                yield _encode_sse_event(
                    event="done",
                    data=done_payload,
                    event_id=current_seq,
                )
                break

            if time.monotonic() - started_at >= max_wait_seconds:
                keepalive_payload = {
                    "seq": current_seq,
                    "pull_job_id": str(job.id),
                    "status": latest_job.status,
                    "stage": latest_job.stage,
                }
                yield _encode_sse_event(
                    event="keepalive",
                    data=keepalive_payload,
                    event_id=current_seq,
                )
                break
            time.sleep(poll_interval_ms / 1000.0)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.delete("/api/v1/system/ai/ollama/models/{model_name}")
def delete_ollama_model_endpoint(
    request: Request,
    model_name: str,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    provider, _probe_result = ensure_system_ollama_provider(db, probe=False)
    if provider is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="系统 Ollama 未配置")
    result = delete_system_ollama_model_by_name(db, provider=provider, name=model_name)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="system.ai.ollama.model.deleted",
        resource_type="SYSTEM_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json={"model": model_name, "result": result},
    )
    db.commit()
    return success_response(request, data={"ok": True, "result": result})


@router.get("/api/v1/me/ai/providers")
def list_my_ai_providers(
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    items = [
        UserAIProviderPayload(**build_user_ai_provider_payload(item))
        for item in list_user_ai_providers(db, user_id=principal.user.id)
    ]
    data = UserAIProviderListPayload(items=items, total=len(items))
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/me/ai/options")
def get_my_ai_options(
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    data = AIProviderOptionsPayload(
        **build_ai_provider_options_payload(db, user_id=principal.user.id)
    )
    db.commit()
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/me/ai/model-catalog")
def get_my_ai_model_catalog(
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    data = AIModelCatalogPayload(
        **build_ai_model_catalog_payload(db, user_id=principal.user.id)
    )
    db.commit()
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/me/ai/providers")
def create_my_ai_provider(
    request: Request,
    payload: UserAIProviderCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    provider = create_user_ai_provider(
        db,
        user_id=principal.user.id,
        display_name=payload.display_name,
        vendor_name=payload.vendor_name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        default_model=payload.default_model,
        timeout_seconds=payload.timeout_seconds,
        temperature=payload.temperature,
        enabled=payload.enabled,
        is_default=payload.is_default,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.ai.provider.created",
        resource_type="USER_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json={
            "display_name": provider.display_name,
            "vendor_name": provider.vendor_name,
            "base_url": provider.base_url,
            "default_model": provider.default_model,
            "is_default": provider.is_default,
        },
    )
    db.commit()
    db.refresh(provider)
    data = UserAIProviderPayload(**build_user_ai_provider_payload(provider))
    return success_response(request, data=data.model_dump(), status_code=201)


@router.post("/api/v1/me/ai/providers/test-draft")
def test_my_ai_provider_draft(
    request: Request,
    payload: AIProviderDraftTestRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    result = AIProviderDraftTestPayload(
        **probe_user_ai_provider_draft(
            db,
            user_id=principal.user.id,
            vendor_name=payload.vendor_name,
            base_url=payload.base_url,
            api_key=payload.api_key,
            timeout_seconds=payload.timeout_seconds,
            selected_model=payload.selected_model,
            verify_selected_model=payload.verify_selected_model,
        )
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.ai.provider.draft_tested",
        resource_type="USER_AI_PROVIDER_DRAFT",
        resource_id=None,
        detail_json={
            "vendor_name": result.vendor_name,
            "base_url": result.base_url,
            "model_count": result.model_count,
            "selected_model_verification": (
                result.selected_model_verification.model_dump()
                if result.selected_model_verification is not None
                else None
            ),
        },
    )
    db.commit()
    return success_response(request, data=result.model_dump())


@router.get("/api/v1/me/ai/providers/{provider_id}")
def get_my_ai_provider(
    request: Request,
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    data = UserAIProviderPayload(
        **build_user_ai_provider_payload(
            get_user_ai_provider(db, user_id=principal.user.id, provider_id=provider_id)
        )
    )
    return success_response(request, data=data.model_dump())


@router.patch("/api/v1/me/ai/providers/{provider_id}")
def update_my_ai_provider(
    request: Request,
    provider_id: uuid.UUID,
    payload: UserAIProviderUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    provider = get_user_ai_provider(
        db, user_id=principal.user.id, provider_id=provider_id
    )
    provider = update_user_ai_provider(
        db,
        provider=provider,
        display_name=payload.display_name,
        vendor_name=payload.vendor_name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        default_model=payload.default_model,
        timeout_seconds=payload.timeout_seconds,
        temperature=payload.temperature,
        enabled=payload.enabled,
        is_default=payload.is_default,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.ai.provider.updated",
        resource_type="USER_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json={
            "display_name": provider.display_name,
            "vendor_name": provider.vendor_name,
            "base_url": provider.base_url,
            "default_model": provider.default_model,
            "is_default": provider.is_default,
            "enabled": provider.enabled,
        },
    )
    db.commit()
    db.refresh(provider)
    data = UserAIProviderPayload(**build_user_ai_provider_payload(provider))
    return success_response(request, data=data.model_dump())


@router.delete("/api/v1/me/ai/providers/{provider_id}")
def delete_my_ai_provider(
    request: Request,
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    provider = get_user_ai_provider(
        db, user_id=principal.user.id, provider_id=provider_id
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.ai.provider.deleted",
        resource_type="USER_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json={"display_name": provider.display_name},
    )
    delete_user_ai_provider(db, provider=provider)
    db.commit()
    return success_response(request, data={"ok": True, "provider_id": str(provider_id)})


@router.post("/api/v1/me/ai/providers/{provider_id}/test")
def test_my_ai_provider(
    request: Request,
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    provider = get_user_ai_provider(
        db, user_id=principal.user.id, provider_id=provider_id
    )
    result = AIProviderTestPayload(**test_user_ai_provider(provider))
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.ai.provider.tested",
        resource_type="USER_AI_PROVIDER",
        resource_id=str(provider.id),
        detail_json=result.detail,
    )
    db.commit()
    return success_response(request, data=result.model_dump())


@router.get("/api/v1/jobs/{job_id}/ai-enrichment")
def get_scan_ai_enrichment_status(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "job:read", resource_type="JOB", resource_id_param="job_id"
        )
    ),
):
    scan_job = db.get(Job, job_id)
    if scan_job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
    if scan_job.job_type != "SCAN":
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="仅支持扫描任务"
        )
    ai_block = (
        scan_job.payload.get("ai") if isinstance(scan_job.payload, dict) else None
    )
    related_jobs = [
        build_ai_job_summary(item)
        for item in list_scan_related_ai_jobs(db, scan_job_id=job_id)
    ]
    latest = related_jobs[0]["id"] if related_jobs else None
    latest_status = related_jobs[0]["status"] if related_jobs else None
    data = AIEnrichmentJobPayload(
        scan_job_id=job_id,
        enabled=bool(isinstance(ai_block, dict) and ai_block.get("enabled")),
        latest_job_id=latest,
        latest_status=latest_status,
        jobs=related_jobs,
    )
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/findings/{finding_id}/ai/assessments")
def get_finding_ai_assessments(
    request: Request,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    items = [
        FindingAIAssessmentPayload(**build_finding_ai_assessment_payload(item))
        for item in list_finding_ai_assessments(db, finding_id=finding_id)
    ]
    data = FindingAIAssessmentListPayload(items=items, total=len(items))
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/findings/{finding_id}/ai/assessment/latest")
def get_latest_finding_assessment(
    request: Request,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    assessment = get_latest_finding_ai_assessment(db, finding_id=finding_id)
    data = (
        FindingAIAssessmentPayload(
            **build_finding_ai_assessment_payload(assessment)
        ).model_dump()
        if assessment is not None
        else None
    )
    return success_response(request, data=data)


@router.get("/api/v1/findings/{finding_id}/ai/assessment/latest/context")
def get_latest_finding_assessment_context(
    request: Request,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    assessment = get_latest_finding_ai_assessment(db, finding_id=finding_id)
    if assessment is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="AI 研判结果不存在")
    data = FindingAIAssessmentContextPayload(
        assessment_id=assessment.id,
        finding_id=assessment.finding_id,
        request_messages=assessment.request_messages_json,
        context_snapshot=assessment.context_snapshot_json,
        response_text=assessment.response_text,
        summary_json=assessment.summary_json,
    )
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/findings/{finding_id}/ai/retry")
def retry_finding_ai(
    request: Request,
    finding_id: uuid.UUID,
    payload: AIProviderSelectionRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")
    snapshot = resolve_provider_snapshot(
        db,
        user_id=principal.user.id,
        ai_source=payload.ai_source,
        ai_provider_id=payload.ai_provider_id,
        ai_model=payload.ai_model,
    )
    job = create_finding_retry_ai_job(
        db,
        finding=finding,
        request_id=get_request_id(request),
        created_by=principal.user.id,
        provider_snapshot=snapshot,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="finding.ai.retry.triggered",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=finding.project_id,
        detail_json={"finding_id": str(finding.id), "scan_job_id": str(finding.job_id)},
    )
    db.commit()
    try:
        dispatch_ai_job(db, job=job)
    except AppError:
        mark_ai_dispatch_failed(
            db,
            job_id=job.id,
            request_id=get_request_id(request),
            operator_user_id=principal.user.id,
        )
        raise
    data = JobTriggerPayload(job_id=job.id, idempotent_replay=False)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.post("/api/v1/findings/{finding_id}/ai/chat/sessions/from-latest-assessment")
def create_assessment_seed_chat_session_endpoint(
    request: Request,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")
    assessment = get_latest_finding_ai_assessment(db, finding_id=finding_id)
    if assessment is None:
        raise AppError(
            code="NOT_FOUND",
            status_code=404,
            message="当前漏洞还没有可承接的 AI 研判结果",
        )
    if assessment.status != AIAssessmentStatus.SUCCEEDED.value:
        raise AppError(
            code="AI_ASSESSMENT_NOT_READY",
            status_code=409,
            message="当前最新 AI 研判尚未成功，暂时无法创建承接会话",
        )
    session, idempotent_replay = create_assessment_seed_chat_session(
        db,
        finding=finding,
        assessment=assessment,
        created_by=principal.user.id,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action=(
            "finding.ai.chat.session.reused"
            if idempotent_replay
            else "finding.ai.chat.session.seeded"
        ),
        resource_type="AI_CHAT_SESSION",
        resource_id=str(session.id),
        project_id=finding.project_id,
        detail_json={
            "finding_id": str(finding.id),
            "assessment_id": str(assessment.id),
        },
    )
    db.commit()
    data = AIAssessmentChatSessionTriggerPayload(
        ok=True,
        session_id=session.id,
        assessment_id=assessment.id,
        idempotent_replay=idempotent_replay,
    )
    return success_response(request, data=data.model_dump(), status_code=200)


@router.get("/api/v1/findings/{finding_id}/ai/chat/sessions")
def list_finding_chat_sessions_endpoint(
    request: Request,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    items = [
        AIChatSessionPayload(**build_chat_session_payload(item))
        for item in list_chat_sessions(db, finding_id=finding_id)
    ]
    data = AIChatSessionListPayload(items=items, total=len(items))
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/me/ai/chat/sessions")
def list_my_chat_sessions_endpoint(
    request: Request,
    finding_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    if finding_id is not None:
        ensure_resource_action(
            db=db,
            user_id=principal.user.id,
            role=principal.user.role,
            action="finding:read",
            resource_type="FINDING",
            resource_id=finding_id,
        )
    items = [
        AIChatSessionPayload(**build_chat_session_payload(item))
        for item in list_user_chat_sessions(
            db, user_id=principal.user.id, finding_id=finding_id
        )
    ]
    data = AIChatSessionListPayload(items=items, total=len(items))
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/me/ai/chat/sessions")
def create_general_chat_session_endpoint(
    request: Request,
    payload: AIChatSessionCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    snapshot = resolve_provider_snapshot(
        db,
        user_id=principal.user.id,
        ai_source=payload.ai_source,
        ai_provider_id=payload.ai_provider_id,
        ai_model=payload.ai_model,
    )
    session = create_general_chat_session(
        db,
        created_by=principal.user.id,
        provider_snapshot=snapshot,
        title=payload.title,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="ai.chat.session.created",
        resource_type="AI_CHAT_SESSION",
        resource_id=str(session.id),
        detail_json={
            "session_mode": session.session_mode,
            "provider_source": session.provider_source,
        },
    )
    db.commit()
    db.refresh(session)
    data = AIChatSessionPayload(**build_chat_session_payload(session))
    return success_response(request, data=data.model_dump(), status_code=201)


@router.post("/api/v1/findings/{finding_id}/ai/chat/sessions")
def create_finding_chat_session_endpoint(
    request: Request,
    finding_id: uuid.UUID,
    payload: AIChatSessionCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read", resource_type="FINDING", resource_id_param="finding_id"
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")
    snapshot = resolve_provider_snapshot(
        db,
        user_id=principal.user.id,
        ai_source=payload.ai_source,
        ai_provider_id=payload.ai_provider_id,
        ai_model=payload.ai_model,
    )
    session = create_chat_session(
        db,
        finding=finding,
        created_by=principal.user.id,
        provider_snapshot=snapshot,
        title=payload.title,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="finding.ai.chat.session.created",
        resource_type="AI_CHAT_SESSION",
        resource_id=str(session.id),
        project_id=finding.project_id,
        detail_json={
            "session_mode": session.session_mode,
            "finding_id": str(finding.id),
            "provider_source": session.provider_source,
        },
    )
    db.commit()
    db.refresh(session)
    data = AIChatSessionPayload(**build_chat_session_payload(session))
    return success_response(request, data=data.model_dump(), status_code=201)


@router.get("/api/v1/ai/chat/sessions/{session_id}")
def get_chat_session_endpoint(
    request: Request,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    session = _ensure_chat_session_access(
        db=db, principal=principal, session_id=session_id
    )
    messages = list_chat_messages(db, session_id=session.id)
    data = AIChatSessionPayload(
        **build_chat_session_payload(session, messages=messages)
    )
    return success_response(request, data=data.model_dump())


@router.delete("/api/v1/ai/chat/sessions/{session_id}")
def delete_chat_session_endpoint(
    request: Request,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    session = _ensure_chat_session_owner_access(
        db=db, principal=principal, session_id=session_id
    )
    payload = AIChatSessionDeletePayload(ok=True, session_id=session.id)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="ai.chat.session.deleted",
        resource_type="AI_CHAT_SESSION",
        resource_id=str(session.id),
        project_id=session.project_id,
        detail_json={
            "session_mode": session.session_mode,
            "finding_id": str(session.finding_id) if session.finding_id else None,
        },
    )
    delete_chat_session(db, session=session)
    db.commit()
    return success_response(request, data=payload.model_dump())


@router.patch("/api/v1/ai/chat/sessions/{session_id}/selection")
def update_chat_session_selection_endpoint(
    request: Request,
    session_id: uuid.UUID,
    payload: AIChatSessionSelectionUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    session = _ensure_chat_session_access(
        db=db, principal=principal, session_id=session_id
    )
    snapshot = resolve_provider_snapshot(
        db,
        user_id=principal.user.id,
        ai_source=payload.ai_source,
        ai_provider_id=payload.ai_provider_id,
        ai_model=payload.ai_model,
    )
    session = update_chat_session_selection(
        db,
        session=session,
        provider_snapshot=snapshot,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="ai.chat.session.selection.updated",
        resource_type="AI_CHAT_SESSION",
        resource_id=str(session.id),
        project_id=session.project_id,
        detail_json={
            "session_mode": session.session_mode,
            "provider_source": session.provider_source,
            "model_name": session.model_name,
        },
    )
    db.commit()
    db.refresh(session)
    data = AIChatSessionPayload(**build_chat_session_payload(session))
    return success_response(request, data=data.model_dump())


@router.post("/api/v1/ai/chat/sessions/{session_id}/messages")
def send_chat_message_endpoint(
    request: Request,
    session_id: uuid.UUID,
    payload: AIChatMessageCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    session = _ensure_chat_session_access(
        db=db, principal=principal, session_id=session_id
    )
    finding = db.get(Finding, session.finding_id) if session.finding_id else None
    if session.finding_id is not None and finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")
    user_message, assistant_message = send_chat_message(
        db,
        session=session,
        finding=finding,
        content=payload.content,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="ai.chat.message.sent",
        resource_type="AI_CHAT_SESSION",
        resource_id=str(session.id),
        project_id=finding.project_id if finding is not None else None,
        detail_json={
            "session_mode": session.session_mode,
            "finding_id": str(finding.id) if finding is not None else None,
        },
    )
    db.commit()
    data = {
        "user_message": AIChatMessagePayload(
            **build_chat_message_payload(user_message)
        ).model_dump(),
        "assistant_message": AIChatMessagePayload(
            **build_chat_message_payload(assistant_message)
        ).model_dump(),
    }
    return success_response(request, data=data, status_code=201)


@router.post("/api/v1/ai/chat/sessions/{session_id}/messages/stream")
def send_chat_message_stream_endpoint(
    request: Request,
    session_id: uuid.UUID,
    payload: AIChatMessageCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    session = _ensure_chat_session_access(
        db=db, principal=principal, session_id=session_id
    )
    finding = db.get(Finding, session.finding_id) if session.finding_id else None
    if session.finding_id is not None and finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")

    user_message = create_chat_user_message(
        db,
        session=session,
        content=payload.content,
    )
    provider_snapshot, request_messages = prepare_chat_completion_request(
        db,
        session=session,
        finding=finding,
    )
    db.commit()

    user_message_payload = AIChatMessagePayload(
        **build_chat_message_payload(user_message)
    ).model_dump(mode="json")
    request_id = get_request_id(request)
    finding_project_id = finding.project_id if finding is not None else None

    def stream():
        event_id = 0
        assistant_parts: list[str] = []
        raw_events: list[dict[str, object]] = []

        def next_event_id() -> int:
            nonlocal event_id
            event_id += 1
            return event_id

        try:
            yield _encode_sse_event(
                event="user_message",
                data=user_message_payload,
                event_id=next_event_id(),
            )
            for chunk in iter_provider_chat_stream(
                provider_snapshot=provider_snapshot,
                messages=request_messages,
            ):
                raw_events.append(dict(chunk.raw_payload))
                if chunk.content:
                    assistant_parts.append(chunk.content)
                    yield _encode_sse_event(
                        event="assistant_delta",
                        data={"delta": chunk.content},
                        event_id=next_event_id(),
                    )

            assistant_content = "".join(assistant_parts).strip()
            if not assistant_content:
                raise AppError(
                    code="AI_EMPTY_RESPONSE",
                    status_code=502,
                    message="AI 未返回有效内容",
                )

            assistant_message = create_chat_assistant_message(
                db,
                session=session,
                content=assistant_content,
                raw_payload={"events": raw_events},
            )
            append_audit_log(
                db,
                request_id=request_id,
                operator_user_id=principal.user.id,
                action="ai.chat.message.sent",
                resource_type="AI_CHAT_SESSION",
                resource_id=str(session.id),
                project_id=finding_project_id,
                detail_json={
                    "session_mode": session.session_mode,
                    "finding_id": str(finding.id) if finding is not None else None,
                    "stream": True,
                },
            )
            db.commit()

            assistant_message_payload = AIChatMessagePayload(
                **build_chat_message_payload(assistant_message)
            ).model_dump(mode="json")
            yield _encode_sse_event(
                event="assistant_message",
                data=assistant_message_payload,
                event_id=next_event_id(),
            )
            yield _encode_sse_event(
                event="done",
                data={
                    "session_id": str(session.id),
                    "user_message_id": user_message_payload["id"],
                    "assistant_message_id": assistant_message_payload["id"],
                },
                event_id=next_event_id(),
            )
        except AppError as exc:
            db.rollback()
            append_audit_log(
                db,
                request_id=request_id,
                operator_user_id=principal.user.id,
                action="ai.chat.message.failed",
                resource_type="AI_CHAT_SESSION",
                resource_id=str(session.id),
                project_id=finding_project_id,
                error_code=exc.code,
                detail_json={
                    "session_mode": session.session_mode,
                    "finding_id": str(finding.id) if finding is not None else None,
                    "stream": True,
                    **exc.detail,
                },
            )
            db.commit()
            yield _encode_sse_event(
                event="error",
                data={
                    "code": exc.code,
                    "message": exc.message,
                    "detail": exc.detail,
                },
                event_id=next_event_id(),
            )
        except Exception as exc:
            db.rollback()
            append_audit_log(
                db,
                request_id=request_id,
                operator_user_id=principal.user.id,
                action="ai.chat.message.failed",
                resource_type="AI_CHAT_SESSION",
                resource_id=str(session.id),
                project_id=finding_project_id,
                error_code="AI_STREAM_ERROR",
                detail_json={
                    "session_mode": session.session_mode,
                    "finding_id": str(finding.id) if finding is not None else None,
                    "stream": True,
                    "error": str(exc),
                },
            )
            db.commit()
            yield _encode_sse_event(
                event="error",
                data={
                    "code": "AI_STREAM_ERROR",
                    "message": "AI 响应流异常中断",
                },
                event_id=next_event_id(),
            )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=headers,
    )
