from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    AIChatMessage,
    AIChatRole,
    AIChatSession,
    AIChatSessionMode,
    AIAssessmentStatus,
    AIProviderType,
    Finding,
    FindingAIAssessment,
    Job,
    JobStage,
    JobStatus,
    JobStep,
    JobStepStatus,
    JobType,
    SystemAIProvider,
    TaskLogType,
    UserAIProvider,
    utc_now,
)
from app.security.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.services.ai_client_service import (
    delete_ollama_model,
    list_ollama_models,
    list_openai_compatible_models,
    pull_ollama_model,
    run_provider_chat,
    test_ollama_connection,
    test_openai_compatible_connection,
)
from app.services.audit_service import append_audit_log
from app.services.task_log_service import append_task_log


SYSTEM_OLLAMA_PROVIDER_KEY = "system_ollama"
AI_SOURCE_SYSTEM_OLLAMA = "system_ollama"
AI_SOURCE_USER_EXTERNAL = "user_external"

AI_STEP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("prepare", "准备上下文"),
    ("ai", "AI 研判"),
    ("cleanup", "写入结果"),
)

TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELED.value,
    JobStatus.TIMEOUT.value,
}
TERMINAL_STEP_STATUSES = {
    JobStepStatus.SUCCEEDED.value,
    JobStepStatus.FAILED.value,
    JobStepStatus.CANCELED.value,
}

ASSESSMENT_SYSTEM_PROMPT = (
    "你是代码安全研判助手。请只基于给定证据和代码上下文进行判断，不要臆造未提供的信息。"
    "输出 JSON，字段包含 verdict, confidence, summary, risk_reason, false_positive_signals,"
    " fix_suggestions, evidence_refs。"
    "verdict 只能是 TP、FP、NEEDS_REVIEW 之一；confidence 只能是 high、medium、low 之一。"
)

CHAT_SYSTEM_PROMPT = (
    "你是代码安全分析助手。回答时仅基于当前漏洞证据、代码上下文、历史 AI 研判和用户问题。"
    "如果证据不足，明确说明需要更多上下文。不要输出攻击载荷。"
)

GENERAL_CHAT_SYSTEM_PROMPT = (
    "你是代码安全与工程辅助助手。可以直接和用户讨论代码、安全、架构、漏洞修复、"
    "模型能力等话题。回答时保持专业、准确、简洁；如果缺少上下文，明确指出需要补充信息。"
)


@dataclass(slots=True)
class AssessmentRunResult:
    assessment: FindingAIAssessment
    ok: bool


def get_system_ollama_provider(db: Session) -> SystemAIProvider | None:
    return db.scalar(
        select(SystemAIProvider).where(
            SystemAIProvider.provider_key == SYSTEM_OLLAMA_PROVIDER_KEY
        )
    )


def ensure_system_ollama_provider(
    db: Session, *, probe: bool = False
) -> tuple[SystemAIProvider | None, dict[str, object]]:
    settings = get_settings()
    provider = get_system_ollama_provider(db)
    auto_configured = False

    if provider is None and settings.ai_system_ollama_auto_configure:
        provider = SystemAIProvider(
            provider_key=SYSTEM_OLLAMA_PROVIDER_KEY,
            display_name=str(settings.ai_system_ollama_display_name).strip()
            or "System Ollama",
            provider_type=AIProviderType.OLLAMA_LOCAL.value,
            base_url=_normalize_url(settings.ai_system_ollama_base_url),
            enabled=True,
            default_model=_normalize_optional_text(
                settings.ai_system_ollama_default_model
            ),
            published_models_json=[],
            timeout_seconds=int(settings.ai_default_timeout_seconds),
            temperature=float(settings.ai_default_temperature),
        )
        db.add(provider)
        db.flush()
        auto_configured = True

    probe_result: dict[str, object] = {
        "auto_configured": auto_configured,
        "connection_ok": None,
        "connection_detail": {},
    }
    if provider is None or not probe:
        return provider, probe_result

    last_error: AppError | None = None
    working_base_url: str | None = None
    models: list[dict[str, object]] | None = None
    for candidate_url in _candidate_ollama_urls(provider.base_url):
        try:
            models = list_ollama_models(
                base_url=candidate_url,
                timeout_seconds=int(provider.timeout_seconds),
            )
            working_base_url = candidate_url
            break
        except AppError as exc:
            last_error = exc

    try:
        if models is None or working_base_url is None:
            if last_error is not None:
                raise last_error
            raise AppError(
                code="AI_PROVIDER_UNAVAILABLE",
                status_code=503,
                message="系统 Ollama 当前不可用",
            )

        provider.base_url = working_base_url
        model_names = [
            str(item.get("name") or "").strip()
            for item in models
            if str(item.get("name") or "").strip()
        ]
        if not provider.published_models_json and model_names:
            provider.published_models_json = model_names
        if not provider.default_model and model_names:
            provider.default_model = model_names[0]
        db.flush()
        probe_result["connection_ok"] = True
        probe_result["connection_detail"] = {
            "base_url": working_base_url,
            "model_count": len(model_names),
            "discovered_models": model_names,
        }
    except AppError as exc:
        probe_result["connection_ok"] = False
        probe_result["connection_detail"] = {
            "base_url": provider.base_url,
            "error_code": exc.code,
            "message": exc.message,
            "detail": exc.detail or {},
        }
    return provider, probe_result


def upsert_system_ollama_provider(
    db: Session,
    *,
    display_name: str,
    base_url: str,
    enabled: bool,
    default_model: str | None,
    published_models: list[str],
    timeout_seconds: int,
    temperature: float,
) -> SystemAIProvider:
    provider = get_system_ollama_provider(db)
    if provider is None:
        provider = SystemAIProvider(
            provider_key=SYSTEM_OLLAMA_PROVIDER_KEY,
            display_name=display_name,
            provider_type=AIProviderType.OLLAMA_LOCAL.value,
            base_url=_normalize_url(base_url),
            enabled=enabled,
            default_model=_normalize_optional_text(default_model),
            published_models_json=_normalize_model_list(published_models),
            timeout_seconds=timeout_seconds,
            temperature=temperature,
        )
        db.add(provider)
        db.flush()
        return provider

    provider.display_name = display_name
    provider.base_url = _normalize_url(base_url)
    provider.enabled = bool(enabled)
    provider.default_model = _normalize_optional_text(default_model)
    provider.published_models_json = _normalize_model_list(published_models)
    provider.timeout_seconds = int(timeout_seconds)
    provider.temperature = float(temperature)
    db.flush()
    return provider


def build_system_ollama_payload(
    provider: SystemAIProvider | None,
    *,
    auto_configured: bool = False,
    connection_ok: bool | None = None,
    connection_detail: dict[str, object] | None = None,
) -> dict[str, object]:
    if provider is None:
        settings = get_settings()
        return {
            "id": None,
            "provider_key": SYSTEM_OLLAMA_PROVIDER_KEY,
            "display_name": settings.ai_system_ollama_display_name,
            "provider_type": AIProviderType.OLLAMA_LOCAL.value,
            "base_url": settings.ai_system_ollama_base_url,
            "enabled": False,
            "default_model": _normalize_optional_text(
                settings.ai_system_ollama_default_model
            ),
            "published_models": [],
            "timeout_seconds": int(settings.ai_default_timeout_seconds),
            "temperature": float(settings.ai_default_temperature),
            "is_configured": False,
            "auto_configured": auto_configured,
            "connection_ok": connection_ok,
            "connection_detail": connection_detail or {},
            "created_at": None,
            "updated_at": None,
        }
    return {
        "id": provider.id,
        "provider_key": provider.provider_key,
        "display_name": provider.display_name,
        "provider_type": provider.provider_type,
        "base_url": provider.base_url,
        "enabled": provider.enabled,
        "default_model": provider.default_model,
        "published_models": _normalize_model_list(provider.published_models_json),
        "timeout_seconds": int(provider.timeout_seconds),
        "temperature": float(provider.temperature),
        "is_configured": True,
        "auto_configured": auto_configured,
        "connection_ok": connection_ok,
        "connection_detail": connection_detail or {},
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def list_user_ai_providers(db: Session, *, user_id: uuid.UUID) -> list[UserAIProvider]:
    return db.scalars(
        select(UserAIProvider)
        .where(UserAIProvider.user_id == user_id)
        .order_by(UserAIProvider.is_default.desc(), UserAIProvider.created_at.desc())
    ).all()


def get_user_ai_provider(
    db: Session, *, user_id: uuid.UUID, provider_id: uuid.UUID
) -> UserAIProvider:
    provider = db.scalar(
        select(UserAIProvider).where(
            UserAIProvider.id == provider_id, UserAIProvider.user_id == user_id
        )
    )
    if provider is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="AI Provider 不存在")
    return provider


def create_user_ai_provider(
    db: Session,
    *,
    user_id: uuid.UUID,
    display_name: str,
    vendor_name: str,
    base_url: str,
    api_key: str,
    default_model: str,
    timeout_seconds: int,
    temperature: float,
    enabled: bool,
    is_default: bool,
) -> UserAIProvider:
    provider = UserAIProvider(
        user_id=user_id,
        display_name=_normalize_required_text(display_name, field_name="display_name"),
        vendor_name=_normalize_required_text(vendor_name, field_name="vendor_name"),
        provider_type=AIProviderType.OPENAI_COMPATIBLE.value,
        base_url=_normalize_url(base_url),
        api_key_encrypted=encrypt_secret(api_key),
        default_model=_normalize_required_text(
            default_model, field_name="default_model"
        ),
        timeout_seconds=int(timeout_seconds),
        temperature=float(temperature),
        enabled=bool(enabled),
        is_default=bool(is_default),
    )
    db.add(provider)
    db.flush()
    if provider.is_default:
        _unset_other_user_defaults(db, user_id=user_id, provider_id=provider.id)
    return provider


def update_user_ai_provider(
    db: Session,
    *,
    provider: UserAIProvider,
    display_name: str | None = None,
    vendor_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    default_model: str | None = None,
    timeout_seconds: int | None = None,
    temperature: float | None = None,
    enabled: bool | None = None,
    is_default: bool | None = None,
) -> UserAIProvider:
    if display_name is not None:
        provider.display_name = _normalize_required_text(
            display_name, field_name="display_name"
        )
    if vendor_name is not None:
        provider.vendor_name = _normalize_required_text(
            vendor_name, field_name="vendor_name"
        )
    if base_url is not None:
        provider.base_url = _normalize_url(base_url)
    if api_key is not None:
        provider.api_key_encrypted = encrypt_secret(api_key)
    if default_model is not None:
        provider.default_model = _normalize_required_text(
            default_model, field_name="default_model"
        )
    if timeout_seconds is not None:
        provider.timeout_seconds = int(timeout_seconds)
    if temperature is not None:
        provider.temperature = float(temperature)
    if enabled is not None:
        provider.enabled = bool(enabled)
    if is_default is not None:
        provider.is_default = bool(is_default)
    db.flush()
    if provider.is_default:
        _unset_other_user_defaults(
            db, user_id=provider.user_id, provider_id=provider.id
        )
    return provider


def delete_user_ai_provider(db: Session, *, provider: UserAIProvider) -> None:
    db.delete(provider)
    db.flush()


def build_user_ai_provider_payload(provider: UserAIProvider) -> dict[str, object]:
    api_key = decrypt_secret(provider.api_key_encrypted)
    return {
        "id": provider.id,
        "user_id": provider.user_id,
        "display_name": provider.display_name,
        "vendor_name": provider.vendor_name,
        "provider_type": provider.provider_type,
        "base_url": provider.base_url,
        "default_model": provider.default_model,
        "timeout_seconds": int(provider.timeout_seconds),
        "temperature": float(provider.temperature),
        "enabled": provider.enabled,
        "is_default": provider.is_default,
        "has_api_key": True,
        "api_key_masked": mask_secret(api_key),
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def test_system_ollama_provider(provider: SystemAIProvider) -> dict[str, object]:
    detail = test_ollama_connection(
        base_url=provider.base_url,
        timeout_seconds=int(provider.timeout_seconds),
    )
    return {
        "ok": True,
        "provider_type": provider.provider_type,
        "provider_label": provider.display_name,
        "detail": detail,
    }


def get_ollama_model_payloads(provider: SystemAIProvider) -> list[dict[str, object]]:
    models = list_ollama_models(
        base_url=provider.base_url,
        timeout_seconds=int(provider.timeout_seconds),
    )
    items: list[dict[str, object]] = []
    for item in models:
        items.append(
            {
                "name": str(item.get("name") or ""),
                "size": _to_int(item.get("size")),
                "digest": _normalize_optional_text(item.get("digest")),
                "modified_at": _normalize_optional_text(item.get("modified_at")),
                "details": dict(item.get("details"))
                if isinstance(item.get("details"), dict)
                else {},
            }
        )
    return items


def pull_system_ollama_model(
    db: Session, *, provider: SystemAIProvider, name: str
) -> dict[str, object]:
    result = pull_ollama_model(
        base_url=provider.base_url,
        name=name,
        timeout_seconds=max(int(provider.timeout_seconds), 300),
    )
    normalized_name = _normalize_required_text(name, field_name="name")
    models = _normalize_model_list(provider.published_models_json)
    if normalized_name not in models:
        models.append(normalized_name)
        provider.published_models_json = models
    if not provider.default_model:
        provider.default_model = normalized_name
    db.flush()
    return result


def delete_system_ollama_model_by_name(
    db: Session, *, provider: SystemAIProvider, name: str
) -> dict[str, object]:
    result = delete_ollama_model(
        base_url=provider.base_url,
        name=name,
        timeout_seconds=int(provider.timeout_seconds),
    )
    normalized_name = _normalize_required_text(name, field_name="name")
    provider.published_models_json = [
        item
        for item in _normalize_model_list(provider.published_models_json)
        if item != normalized_name
    ]
    if provider.default_model == normalized_name:
        provider.default_model = (
            provider.published_models_json[0]
            if provider.published_models_json
            else None
        )
    db.flush()
    return result


def test_user_ai_provider(provider: UserAIProvider) -> dict[str, object]:
    detail = test_openai_compatible_connection(
        base_url=provider.base_url,
        api_key=decrypt_secret(provider.api_key_encrypted),
        timeout_seconds=int(provider.timeout_seconds),
    )
    return {
        "ok": True,
        "provider_type": provider.provider_type,
        "provider_label": provider.display_name,
        "detail": detail,
    }


def resolve_provider_snapshot(
    db: Session,
    *,
    user_id: uuid.UUID,
    ai_source: str | None,
    ai_provider_id: uuid.UUID | None,
    ai_model: str | None,
) -> dict[str, object]:
    normalized_source = _normalize_optional_text(ai_source)
    normalized_model = _normalize_optional_text(ai_model)

    if normalized_source is None:
        if ai_provider_id is not None:
            provider = get_user_ai_provider(
                db, user_id=user_id, provider_id=ai_provider_id
            )
            return _build_user_provider_snapshot(
                provider=provider, override_model=normalized_model
            )

        default_user = db.scalar(
            select(UserAIProvider).where(
                UserAIProvider.user_id == user_id,
                UserAIProvider.is_default.is_(True),
                UserAIProvider.enabled.is_(True),
            )
        )
        if default_user is not None:
            return _build_user_provider_snapshot(
                provider=default_user, override_model=normalized_model
            )

        system_provider, probe_result = ensure_system_ollama_provider(db, probe=True)
        if system_provider is not None and system_provider.enabled:
            if probe_result.get("connection_ok") is False:
                raise AppError(
                    code="AI_PROVIDER_NOT_AVAILABLE",
                    status_code=409,
                    message="系统 Ollama 当前不可用",
                    detail=probe_result.get("connection_detail") or {},
                )
            return _build_system_provider_snapshot(
                provider=system_provider, override_model=normalized_model
            )
        raise AppError(
            code="AI_PROVIDER_NOT_CONFIGURED",
            status_code=422,
            message="当前没有可用的 AI Provider 配置",
        )

    if normalized_source == AI_SOURCE_SYSTEM_OLLAMA:
        provider, probe_result = ensure_system_ollama_provider(db, probe=True)
        if provider is None or not provider.enabled:
            raise AppError(
                code="AI_PROVIDER_NOT_AVAILABLE",
                status_code=409,
                message="系统 Ollama 未启用",
            )
        if probe_result.get("connection_ok") is False:
            raise AppError(
                code="AI_PROVIDER_NOT_AVAILABLE",
                status_code=409,
                message="系统 Ollama 当前不可用",
                detail=probe_result.get("connection_detail") or {},
            )
        return _build_system_provider_snapshot(
            provider=provider, override_model=normalized_model
        )

    if normalized_source == AI_SOURCE_USER_EXTERNAL:
        if ai_provider_id is not None:
            provider = get_user_ai_provider(
                db, user_id=user_id, provider_id=ai_provider_id
            )
        else:
            provider = db.scalar(
                select(UserAIProvider).where(
                    UserAIProvider.user_id == user_id,
                    UserAIProvider.is_default.is_(True),
                    UserAIProvider.enabled.is_(True),
                )
            )
        if provider is None:
            raise AppError(
                code="AI_PROVIDER_NOT_FOUND",
                status_code=404,
                message="未找到可用的用户 AI Provider",
            )
        if not provider.enabled:
            raise AppError(
                code="AI_PROVIDER_DISABLED",
                status_code=409,
                message="所选用户 AI Provider 已被禁用",
            )
        return _build_user_provider_snapshot(
            provider=provider, override_model=normalized_model
        )

    raise AppError(
        code="INVALID_ARGUMENT",
        status_code=422,
        message="ai_source 值不合法",
        detail={"allowed_values": [AI_SOURCE_SYSTEM_OLLAMA, AI_SOURCE_USER_EXTERNAL]},
    )


def sanitize_provider_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    payload = dict(snapshot)
    api_key = _normalize_optional_text(payload.pop("api_key", None))
    encrypted_api_key = _normalize_optional_text(payload.pop("api_key_encrypted", None))
    if api_key is None and encrypted_api_key is not None:
        api_key = decrypt_secret(encrypted_api_key)
    if api_key is not None:
        payload["api_key_masked"] = mask_secret(api_key)
    return payload


def sanitize_job_payload(payload: dict[str, object] | None) -> dict[str, object]:
    data = dict(payload or {})
    ai_block = data.get("ai")
    if isinstance(ai_block, dict):
        copied_ai = dict(ai_block)
        snapshot = copied_ai.get("provider_snapshot")
        if isinstance(snapshot, dict):
            copied_ai["provider_snapshot"] = sanitize_provider_snapshot(snapshot)
        data["ai"] = copied_ai

    snapshot = data.get("provider_snapshot")
    if isinstance(snapshot, dict):
        data["provider_snapshot"] = sanitize_provider_snapshot(snapshot)
    return data


def build_ai_provider_options_payload(
    db: Session, *, user_id: uuid.UUID
) -> dict[str, object]:
    system_provider, probe_result = ensure_system_ollama_provider(db, probe=True)
    user_providers = list_user_ai_providers(db, user_id=user_id)
    default_selection: dict[str, object] = {}

    enabled_user_providers = [item for item in user_providers if item.enabled]
    default_user_provider = next(
        (item for item in enabled_user_providers if item.is_default), None
    )

    if default_user_provider is not None:
        default_selection = {
            "ai_source": AI_SOURCE_USER_EXTERNAL,
            "ai_provider_id": str(default_user_provider.id),
            "ai_model": default_user_provider.default_model,
        }
    elif (
        system_provider is not None
        and system_provider.enabled
        and probe_result.get("connection_ok") is not False
    ):
        default_selection = {
            "ai_source": AI_SOURCE_SYSTEM_OLLAMA,
            "ai_provider_id": None,
            "ai_model": system_provider.default_model
            or _first_published_model(system_provider),
        }

    return {
        "system_ollama": {
            "available": bool(
                system_provider is not None
                and system_provider.enabled
                and probe_result.get("connection_ok") is not False
            ),
            "provider_key": SYSTEM_OLLAMA_PROVIDER_KEY,
            "display_name": system_provider.display_name
            if system_provider
            else "System Ollama",
            "provider_type": (
                system_provider.provider_type
                if system_provider is not None
                else AIProviderType.OLLAMA_LOCAL.value
            ),
            "default_model": system_provider.default_model if system_provider else None,
            "published_models": (
                _normalize_model_list(system_provider.published_models_json)
                if system_provider is not None
                else []
            ),
            "connection_ok": probe_result.get("connection_ok"),
        },
        "user_providers": [
            build_user_ai_provider_payload(item) for item in enabled_user_providers
        ],
        "default_selection": default_selection,
    }


def build_ai_model_catalog_payload(
    db: Session, *, user_id: uuid.UUID
) -> dict[str, object]:
    options = build_ai_provider_options_payload(db, user_id=user_id)
    items: list[dict[str, object]] = []

    system_ollama = options.get("system_ollama") if isinstance(options, dict) else None
    if isinstance(system_ollama, dict) and bool(system_ollama.get("available")):
        system_models = _normalize_model_list(system_ollama.get("published_models"))
        items.append(
            {
                "provider_source": AI_SOURCE_SYSTEM_OLLAMA,
                "provider_id": None,
                "provider_key": SYSTEM_OLLAMA_PROVIDER_KEY,
                "provider_label": str(
                    system_ollama.get("display_name") or "System Ollama"
                ),
                "provider_type": str(
                    system_ollama.get("provider_type")
                    or AIProviderType.OLLAMA_LOCAL.value
                ),
                "enabled": True,
                "models": [
                    {
                        "name": model,
                        "label": model,
                        "is_default": model
                        == _normalize_optional_text(system_ollama.get("default_model")),
                        "details": {},
                    }
                    for model in system_models
                ],
            }
        )

    user_providers = list_user_ai_providers(db, user_id=user_id)
    for provider in user_providers:
        if not provider.enabled:
            continue
        items.append(_build_user_provider_model_catalog_item(provider))

    return {
        "items": items,
        "default_selection": options.get("default_selection")
        if isinstance(options, dict)
        else {},
    }


def update_chat_session_selection(
    db: Session,
    *,
    session: AIChatSession,
    provider_snapshot: dict[str, object],
) -> AIChatSession:
    session.provider_source = str(provider_snapshot.get("source") or "")
    session.provider_type = str(provider_snapshot.get("provider_type") or "")
    session.provider_label = str(provider_snapshot.get("display_name") or "")
    session.model_name = str(provider_snapshot.get("model") or "")
    session.provider_snapshot_json = provider_snapshot
    session.updated_at = utc_now()
    db.flush()
    return session


def build_scan_ai_payload(
    db: Session,
    *,
    user_id: uuid.UUID,
    ai_enabled: bool,
    ai_source: str | None,
    ai_provider_id: uuid.UUID | None,
    ai_model: str | None,
) -> dict[str, object] | None:
    if not ai_enabled:
        return None
    snapshot = resolve_provider_snapshot(
        db,
        user_id=user_id,
        ai_source=ai_source,
        ai_provider_id=ai_provider_id,
        ai_model=ai_model,
    )
    return {
        "enabled": True,
        "mode": "post_scan_enrichment",
        "source": snapshot["source"],
        "provider_snapshot": snapshot,
    }


def create_ai_job(
    db: Session,
    *,
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: dict[str, object],
    created_by: uuid.UUID | None,
) -> Job:
    job = Job(
        project_id=project_id,
        version_id=version_id,
        job_type=JobType.AI.value,
        payload=payload,
        status=JobStatus.PENDING.value,
        stage=JobStage.PREPARE.value,
        created_by=created_by,
        result_summary={},
    )
    db.add(job)
    db.flush()
    initialize_ai_job_steps(db, job_id=job.id)
    return job


def create_scan_enrichment_ai_job(
    db: Session,
    *,
    scan_job: Job,
) -> Job | None:
    ai_payload = (
        scan_job.payload.get("ai") if isinstance(scan_job.payload, dict) else None
    )
    if not isinstance(ai_payload, dict) or not bool(ai_payload.get("enabled")):
        return None
    snapshot = ai_payload.get("provider_snapshot")
    if not isinstance(snapshot, dict):
        return None

    job = create_ai_job(
        db,
        project_id=scan_job.project_id,
        version_id=scan_job.version_id,
        payload={
            "request_id": scan_job.payload.get("request_id"),
            "purpose": "scan_enrichment",
            "scan_job_id": str(scan_job.id),
            "provider_snapshot": snapshot,
        },
        created_by=scan_job.created_by,
    )
    db.flush()
    return job


def create_finding_retry_ai_job(
    db: Session,
    *,
    finding: Finding,
    request_id: str,
    created_by: uuid.UUID,
    provider_snapshot: dict[str, object],
) -> Job:
    job = create_ai_job(
        db,
        project_id=finding.project_id,
        version_id=finding.version_id,
        payload={
            "request_id": request_id,
            "purpose": "finding_retry",
            "scan_job_id": str(finding.job_id),
            "finding_ids": [str(finding.id)],
            "provider_snapshot": provider_snapshot,
        },
        created_by=created_by,
    )
    db.flush()
    return job


def dispatch_ai_job(db: Session, *, job: Job) -> dict[str, object]:
    settings = get_settings()
    backend = (settings.ai_dispatch_backend or "sync").strip().lower()
    allow_fallback = bool(settings.ai_dispatch_fallback_to_sync)

    if backend == "celery":
        try:
            from app.worker.tasks import enqueue_ai_job

            bind = db.get_bind()
            bind_engine = getattr(bind, "engine", bind)
            task_id = enqueue_ai_job(ai_job_id=job.id, db_bind=bind_engine)
            if task_id:
                dispatch_info = {
                    "backend": "celery_or_local",
                    "task_id": task_id,
                    "requested_backend": "celery",
                }
                job.payload = {**(job.payload or {}), "dispatch": dispatch_info}
                _append_ai_log(
                    job_id=job.id,
                    stage=JobStage.PREPARE.value,
                    message=f"AI 任务已投递执行队列，task_id={task_id}",
                    project_id=job.project_id,
                    db=db,
                )
                db.flush()
                return dispatch_info
            if not allow_fallback:
                raise AppError(
                    code="AI_DISPATCH_FAILED",
                    status_code=503,
                    message="AI 任务派发失败",
                )
        except Exception as exc:
            if not allow_fallback:
                raise AppError(
                    code="AI_DISPATCH_FAILED",
                    status_code=503,
                    message="AI 任务派发失败",
                    detail={"reason": str(exc)},
                ) from exc
            dispatch_info = {
                "backend": "sync",
                "task_id": None,
                "requested_backend": "celery",
                "fallback_reason": str(exc),
            }
            job.payload = {**(job.payload or {}), "dispatch": dispatch_info}
            _append_ai_log(
                job_id=job.id,
                stage=JobStage.PREPARE.value,
                message=f"AI 任务派发异常，已回退同步执行: {exc}",
                project_id=job.project_id,
                db=db,
            )
            db.flush()
            run_ai_job(job_id=job.id, db=db)
            return dispatch_info

    dispatch_info = {"backend": "sync", "task_id": None, "requested_backend": backend}
    job.payload = {**(job.payload or {}), "dispatch": dispatch_info}
    _append_ai_log(
        job_id=job.id,
        stage=JobStage.PREPARE.value,
        message="AI 任务以同步模式执行。",
        project_id=job.project_id,
        db=db,
    )
    db.flush()
    run_ai_job(job_id=job.id, db=db)
    return dispatch_info


def mark_ai_dispatch_failed(
    db: Session,
    *,
    job_id: uuid.UUID,
    request_id: str,
    operator_user_id: uuid.UUID | None,
) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.status = JobStatus.FAILED.value
    job.stage = JobStage.PREPARE.value
    job.failure_code = "AI_DISPATCH_FAILED"
    job.failure_stage = JobStage.PREPARE.value
    job.failure_category = "AI"
    job.failure_hint = "AI 任务派发失败，请检查调度器或 Worker 状态。"
    job.finished_at = utc_now()
    if job.started_at is None:
        job.started_at = job.finished_at
    _append_ai_log(
        job_id=job.id,
        stage=JobStage.PREPARE.value,
        message="AI 任务派发失败: code=AI_DISPATCH_FAILED",
        project_id=job.project_id,
        db=db,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="ai.job.dispatch.failed",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        result="FAILED",
        error_code="AI_DISPATCH_FAILED",
    )
    db.commit()


def run_ai_job(*, job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    try:
        job = session.get(Job, job_id)
        if job is None or job.job_type != JobType.AI.value:
            return
        if job.status in TERMINAL_JOB_STATUSES:
            return

        payload = job.payload if isinstance(job.payload, dict) else {}
        provider_snapshot = payload.get("provider_snapshot")
        if not isinstance(provider_snapshot, dict):
            raise AppError(
                code="AI_PROVIDER_NOT_CONFIGURED",
                status_code=422,
                message="AI 任务缺少 Provider 快照",
            )

        request_id = str(payload.get("request_id") or "")
        purpose = str(payload.get("purpose") or "scan_enrichment").strip()

        _set_ai_job_running(session, job=job, stage=JobStage.PREPARE.value)
        findings = _load_target_findings(session, job=job)
        total_findings = len(findings)
        job.result_summary = {
            "purpose": purpose,
            "scan_job_id": payload.get("scan_job_id"),
            "total_findings": total_findings,
            "processed_count": 0,
            "succeeded_count": 0,
            "failed_count": 0,
            "provider": sanitize_provider_snapshot(provider_snapshot),
        }
        _set_ai_step_status(
            session,
            job_id=job.id,
            step_key="prepare",
            status=JobStepStatus.SUCCEEDED.value,
        )

        _set_ai_job_running(session, job=job, stage=JobStage.AI.value)
        _set_ai_step_status(
            session, job_id=job.id, step_key="ai", status=JobStepStatus.RUNNING.value
        )

        succeeded_count = 0
        failed_count = 0
        for index, finding in enumerate(findings, start=1):
            try:
                _run_assessment_for_finding(
                    session,
                    finding=finding,
                    ai_job=job,
                    provider_snapshot=provider_snapshot,
                )
                succeeded_count += 1
                _append_ai_log(
                    job_id=job.id,
                    stage=JobStage.AI.value,
                    message=(
                        f"研判完成: finding_id={finding.id}, progress={index}/{total_findings}"
                    ),
                    project_id=job.project_id,
                    db=session,
                )
            except AppError as exc:
                failed_count += 1
                _record_failed_assessment(
                    session,
                    finding=finding,
                    ai_job=job,
                    provider_snapshot=provider_snapshot,
                    error_code=exc.code,
                    error_message=exc.message,
                )
                _append_ai_log(
                    job_id=job.id,
                    stage=JobStage.AI.value,
                    message=(
                        f"研判失败: finding_id={finding.id}, code={exc.code},"
                        f" progress={index}/{total_findings}"
                    ),
                    project_id=job.project_id,
                    db=session,
                )

            job.result_summary = {
                **(job.result_summary or {}),
                "processed_count": index,
                "succeeded_count": succeeded_count,
                "failed_count": failed_count,
            }
            session.flush()

        _set_ai_step_status(
            session, job_id=job.id, step_key="ai", status=JobStepStatus.SUCCEEDED.value
        )
        _set_ai_job_running(session, job=job, stage=JobStage.CLEANUP.value)
        _set_ai_step_status(
            session,
            job_id=job.id,
            step_key="cleanup",
            status=JobStepStatus.RUNNING.value,
        )

        job.finished_at = utc_now()
        if total_findings > 0 and failed_count >= total_findings:
            job.status = JobStatus.FAILED.value
            job.failure_code = "AI_ALL_ASSESSMENTS_FAILED"
            job.failure_stage = JobStage.AI.value
            job.failure_category = "AI"
            job.failure_hint = (
                "所有漏洞的 AI 研判均失败，请检查 Provider 连通性或提示词约束。"
            )
        else:
            job.status = JobStatus.SUCCEEDED.value
            job.failure_code = None
            job.failure_stage = None
            job.failure_category = None
            job.failure_hint = None
        _append_ai_log(
            job_id=job.id,
            stage=JobStage.CLEANUP.value,
            message=(
                f"AI 任务完成: total={total_findings}, succeeded={succeeded_count}, failed={failed_count}"
            ),
            project_id=job.project_id,
            db=session,
        )
        _set_ai_step_status(
            session,
            job_id=job.id,
            step_key="cleanup",
            status=JobStepStatus.SUCCEEDED.value,
        )
        append_audit_log(
            session,
            request_id=request_id,
            operator_user_id=job.created_by,
            action="ai.job.completed",
            resource_type="JOB",
            resource_id=str(job.id),
            project_id=job.project_id,
            detail_json={
                "purpose": purpose,
                "total_findings": total_findings,
                "succeeded_count": succeeded_count,
                "failed_count": failed_count,
            },
            result=job.status,
            error_code=job.failure_code,
        )
        session.commit()
    except AppError as exc:
        session.rollback()
        _fail_ai_job(
            session,
            job_id=job_id,
            failure_code=exc.code,
            failure_message=exc.message,
        )
    except Exception as exc:
        session.rollback()
        _fail_ai_job(
            session,
            job_id=job_id,
            failure_code="AI_INTERNAL_ERROR",
            failure_message=str(exc),
        )
    finally:
        if owns_db:
            session.close()


def list_finding_ai_assessments(
    db: Session, *, finding_id: uuid.UUID
) -> list[FindingAIAssessment]:
    return db.scalars(
        select(FindingAIAssessment)
        .where(FindingAIAssessment.finding_id == finding_id)
        .order_by(FindingAIAssessment.created_at.desc())
    ).all()


def get_latest_finding_ai_assessment(
    db: Session, *, finding_id: uuid.UUID
) -> FindingAIAssessment | None:
    return db.scalar(
        select(FindingAIAssessment)
        .where(FindingAIAssessment.finding_id == finding_id)
        .order_by(FindingAIAssessment.created_at.desc())
        .limit(1)
    )


def build_finding_ai_assessment_payload(
    assessment: FindingAIAssessment,
) -> dict[str, object]:
    return {
        "id": assessment.id,
        "finding_id": assessment.finding_id,
        "job_id": assessment.job_id,
        "scan_job_id": assessment.scan_job_id,
        "project_id": assessment.project_id,
        "version_id": assessment.version_id,
        "provider_source": assessment.provider_source,
        "provider_type": assessment.provider_type,
        "provider_label": assessment.provider_label,
        "model_name": assessment.model_name,
        "status": assessment.status,
        "summary_json": assessment.summary_json,
        "response_text": assessment.response_text,
        "error_code": assessment.error_code,
        "error_message": assessment.error_message,
        "created_by": assessment.created_by,
        "created_at": assessment.created_at,
        "updated_at": assessment.updated_at,
    }


def list_related_ai_jobs_for_scan(db: Session, *, scan_job_id: uuid.UUID) -> list[Job]:
    return db.scalars(
        select(Job)
        .where(Job.job_type == JobType.AI.value)
        .order_by(Job.created_at.desc())
    ).all()


def list_scan_related_ai_jobs(db: Session, *, scan_job_id: uuid.UUID) -> list[Job]:
    rows = list_related_ai_jobs_for_scan(db, scan_job_id=scan_job_id)
    matched: list[Job] = []
    target = str(scan_job_id)
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if str(payload.get("scan_job_id") or "") == target:
            matched.append(row)
    return matched


def build_ai_job_summary(job: Job) -> dict[str, object]:
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "failure_code": job.failure_code,
        "failure_stage": job.failure_stage,
        "failure_hint": job.failure_hint,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "finished_at": job.finished_at,
        "result_summary": job.result_summary,
    }


def create_general_chat_session(
    db: Session,
    *,
    created_by: uuid.UUID,
    provider_snapshot: dict[str, object],
    title: str | None,
) -> AIChatSession:
    return _create_chat_session_record(
        db,
        session_mode=AIChatSessionMode.GENERAL.value,
        finding=None,
        created_by=created_by,
        provider_snapshot=provider_snapshot,
        title=title,
    )


def create_chat_session(
    db: Session,
    *,
    finding: Finding,
    created_by: uuid.UUID,
    provider_snapshot: dict[str, object],
    title: str | None,
) -> AIChatSession:
    return _create_chat_session_record(
        db,
        session_mode=AIChatSessionMode.FINDING_CONTEXT.value,
        finding=finding,
        created_by=created_by,
        provider_snapshot=provider_snapshot,
        title=title,
    )


def _create_chat_session_record(
    db: Session,
    *,
    session_mode: str,
    finding: Finding | None,
    created_by: uuid.UUID,
    provider_snapshot: dict[str, object],
    title: str | None,
) -> AIChatSession:
    session = AIChatSession(
        session_mode=session_mode,
        finding_id=finding.id if finding is not None else None,
        project_id=finding.project_id if finding is not None else None,
        version_id=finding.version_id if finding is not None else None,
        provider_source=str(provider_snapshot.get("source") or ""),
        provider_type=str(provider_snapshot.get("provider_type") or ""),
        provider_label=str(provider_snapshot.get("display_name") or ""),
        model_name=str(provider_snapshot.get("model") or ""),
        title=_normalize_optional_text(title),
        provider_snapshot_json=provider_snapshot,
        created_by=created_by,
    )
    db.add(session)
    db.flush()
    return session


def list_chat_sessions(db: Session, *, finding_id: uuid.UUID) -> list[AIChatSession]:
    return db.scalars(
        select(AIChatSession)
        .where(AIChatSession.finding_id == finding_id)
        .order_by(AIChatSession.updated_at.desc())
    ).all()


def list_user_chat_sessions(
    db: Session, *, user_id: uuid.UUID, finding_id: uuid.UUID | None = None
) -> list[AIChatSession]:
    stmt = select(AIChatSession).where(AIChatSession.created_by == user_id)
    if finding_id is not None:
        stmt = stmt.where(AIChatSession.finding_id == finding_id)
    return db.scalars(stmt.order_by(AIChatSession.updated_at.desc())).all()


def get_chat_session(db: Session, *, session_id: uuid.UUID) -> AIChatSession:
    session = db.get(AIChatSession, session_id)
    if session is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="AI 会话不存在")
    return session


def delete_chat_session(db: Session, *, session: AIChatSession) -> None:
    db.execute(delete(AIChatMessage).where(AIChatMessage.session_id == session.id))
    db.delete(session)
    db.flush()


def build_chat_session_payload(
    session: AIChatSession,
    *,
    messages: list[AIChatMessage] | None = None,
) -> dict[str, object]:
    return {
        "id": session.id,
        "session_mode": session.session_mode,
        "finding_id": session.finding_id,
        "project_id": session.project_id,
        "version_id": session.version_id,
        "provider_source": session.provider_source,
        "provider_type": session.provider_type,
        "provider_label": session.provider_label,
        "model_name": session.model_name,
        "title": session.title,
        "provider_snapshot": sanitize_provider_snapshot(session.provider_snapshot_json),
        "created_by": session.created_by,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": [build_chat_message_payload(item) for item in (messages or [])],
    }


def list_chat_messages(db: Session, *, session_id: uuid.UUID) -> list[AIChatMessage]:
    return db.scalars(
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at.asc())
    ).all()


def build_chat_message_payload(message: AIChatMessage) -> dict[str, object]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "meta_json": message.meta_json,
        "created_at": message.created_at,
    }


def send_chat_message(
    db: Session,
    *,
    session: AIChatSession,
    finding: Finding | None,
    content: str,
) -> tuple[AIChatMessage, AIChatMessage]:
    user_message = create_chat_user_message(
        db,
        session=session,
        content=content,
    )
    snapshot, messages = prepare_chat_completion_request(
        db,
        session=session,
        finding=finding,
    )
    result = run_provider_chat(provider_snapshot=snapshot, messages=messages)
    assistant_message = create_chat_assistant_message(
        db,
        session=session,
        content=result.content,
        raw_payload=result.raw_payload,
    )
    return user_message, assistant_message


def create_chat_user_message(
    db: Session,
    *,
    session: AIChatSession,
    content: str,
) -> AIChatMessage:
    user_message = AIChatMessage(
        session_id=session.id,
        role=AIChatRole.USER.value,
        content=_normalize_required_text(content, field_name="content"),
        meta_json={},
    )
    db.add(user_message)
    session.updated_at = utc_now()
    if not session.title:
        session.title = _truncate_text(user_message.content, 80)
    db.flush()
    return user_message


def prepare_chat_completion_request(
    db: Session,
    *,
    session: AIChatSession,
    finding: Finding | None,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    history = list_chat_messages(db, session_id=session.id)
    if session.session_mode == AIChatSessionMode.GENERAL.value:
        messages = _build_general_chat_messages(history=history)
    else:
        if finding is None:
            raise AppError(
                code="NOT_FOUND",
                status_code=404,
                message="漏洞不存在",
            )
        latest_assessment = get_latest_finding_ai_assessment(db, finding_id=finding.id)
        messages = _build_chat_messages(
            finding=finding,
            history=history,
            latest_assessment=latest_assessment,
        )
    snapshot = _inflate_provider_snapshot(session.provider_snapshot_json)
    return snapshot, messages


def create_chat_assistant_message(
    db: Session,
    *,
    session: AIChatSession,
    content: str,
    raw_payload: dict[str, object],
) -> AIChatMessage:
    assistant_message = AIChatMessage(
        session_id=session.id,
        role=AIChatRole.ASSISTANT.value,
        content=content,
        meta_json={"raw_payload": raw_payload},
    )
    db.add(assistant_message)
    session.updated_at = utc_now()
    db.flush()
    return assistant_message


def initialize_ai_job_steps(db: Session, *, job_id: uuid.UUID) -> list[JobStep]:
    existing = db.scalars(select(JobStep).where(JobStep.job_id == job_id)).all()
    existing_keys = {item.step_key for item in existing}
    created: list[JobStep] = []
    for index, (step_key, display_name) in enumerate(AI_STEP_DEFINITIONS, start=1):
        if step_key in existing_keys:
            continue
        item = JobStep(
            job_id=job_id,
            step_key=step_key,
            display_name=display_name,
            step_order=index,
            status=JobStepStatus.PENDING.value,
        )
        db.add(item)
        created.append(item)
    if created:
        db.flush()
    return created


def _load_target_findings(db: Session, *, job: Job) -> list[Finding]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    raw_finding_ids = payload.get("finding_ids")
    if isinstance(raw_finding_ids, list) and raw_finding_ids:
        finding_ids: list[uuid.UUID] = []
        for raw in raw_finding_ids:
            try:
                finding_ids.append(uuid.UUID(str(raw)))
            except ValueError:
                continue
        if finding_ids:
            return db.scalars(
                select(Finding)
                .where(Finding.id.in_(finding_ids))
                .order_by(Finding.created_at.asc())
            ).all()

    scan_job_id_raw = _normalize_optional_text(payload.get("scan_job_id"))
    if scan_job_id_raw is None:
        return []
    try:
        scan_job_id = uuid.UUID(scan_job_id_raw)
    except ValueError as exc:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="AI 任务的 scan_job_id 无效",
        ) from exc
    return db.scalars(
        select(Finding)
        .where(Finding.job_id == scan_job_id)
        .order_by(Finding.created_at.asc())
    ).all()


def _run_assessment_for_finding(
    db: Session,
    *,
    finding: Finding,
    ai_job: Job,
    provider_snapshot: dict[str, object],
) -> AssessmentRunResult:
    snapshot = _inflate_provider_snapshot(provider_snapshot)
    messages = _build_assessment_messages(finding=finding)
    result = run_provider_chat(provider_snapshot=snapshot, messages=messages)
    summary = _parse_assessment_content(result.content)
    assessment = db.scalar(
        select(FindingAIAssessment).where(
            FindingAIAssessment.finding_id == finding.id,
            FindingAIAssessment.job_id == ai_job.id,
        )
    )
    if assessment is None:
        assessment = FindingAIAssessment(
            finding_id=finding.id,
            job_id=ai_job.id,
            scan_job_id=_safe_uuid(ai_job.payload.get("scan_job_id")),
            project_id=finding.project_id,
            version_id=finding.version_id,
            provider_source=str(provider_snapshot.get("source") or ""),
            provider_type=str(provider_snapshot.get("provider_type") or ""),
            provider_label=str(provider_snapshot.get("display_name") or ""),
            model_name=str(provider_snapshot.get("model") or ""),
            created_by=ai_job.created_by,
        )
        db.add(assessment)
    assessment.status = AIAssessmentStatus.SUCCEEDED.value
    assessment.summary_json = summary
    assessment.response_text = result.content
    assessment.error_code = None
    assessment.error_message = None
    db.flush()
    return AssessmentRunResult(assessment=assessment, ok=True)


def _record_failed_assessment(
    db: Session,
    *,
    finding: Finding,
    ai_job: Job,
    provider_snapshot: dict[str, object],
    error_code: str,
    error_message: str,
) -> FindingAIAssessment:
    assessment = db.scalar(
        select(FindingAIAssessment).where(
            FindingAIAssessment.finding_id == finding.id,
            FindingAIAssessment.job_id == ai_job.id,
        )
    )
    if assessment is None:
        assessment = FindingAIAssessment(
            finding_id=finding.id,
            job_id=ai_job.id,
            scan_job_id=_safe_uuid(ai_job.payload.get("scan_job_id")),
            project_id=finding.project_id,
            version_id=finding.version_id,
            provider_source=str(provider_snapshot.get("source") or ""),
            provider_type=str(provider_snapshot.get("provider_type") or ""),
            provider_label=str(provider_snapshot.get("display_name") or ""),
            model_name=str(provider_snapshot.get("model") or ""),
            created_by=ai_job.created_by,
        )
        db.add(assessment)
    assessment.status = AIAssessmentStatus.FAILED.value
    assessment.summary_json = {}
    assessment.response_text = None
    assessment.error_code = error_code
    assessment.error_message = error_message
    db.flush()
    return assessment


def _build_system_provider_snapshot(
    *, provider: SystemAIProvider, override_model: str | None
) -> dict[str, object]:
    model = override_model or provider.default_model or _first_published_model(provider)
    if not model:
        raise AppError(
            code="AI_MODEL_NOT_SELECTED",
            status_code=422,
            message="系统 Ollama 尚未配置默认模型",
        )
    return {
        "source": AI_SOURCE_SYSTEM_OLLAMA,
        "provider_id": str(provider.id),
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "base_url": provider.base_url,
        "model": model,
        "timeout_seconds": int(provider.timeout_seconds),
        "temperature": float(provider.temperature),
    }


def _build_user_provider_snapshot(
    *, provider: UserAIProvider, override_model: str | None
) -> dict[str, object]:
    model = override_model or provider.default_model
    if not model:
        raise AppError(
            code="AI_MODEL_NOT_SELECTED",
            status_code=422,
            message="用户 AI Provider 缺少默认模型",
        )
    return {
        "source": AI_SOURCE_USER_EXTERNAL,
        "provider_id": str(provider.id),
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "vendor_name": provider.vendor_name,
        "base_url": provider.base_url,
        "model": model,
        "timeout_seconds": int(provider.timeout_seconds),
        "temperature": float(provider.temperature),
        "api_key_encrypted": provider.api_key_encrypted,
    }


def _build_user_provider_model_catalog_item(
    provider: UserAIProvider,
) -> dict[str, object]:
    models: list[dict[str, object]] = []
    try:
        live_models = list_openai_compatible_models(
            base_url=provider.base_url,
            api_key=decrypt_secret(provider.api_key_encrypted),
            timeout_seconds=int(provider.timeout_seconds),
        )
        for item in live_models:
            model_name = _normalize_optional_text(item.get("id") or item.get("name"))
            if model_name is None:
                continue
            models.append(
                {
                    "name": model_name,
                    "label": model_name,
                    "is_default": model_name == provider.default_model,
                    "details": {
                        key: value
                        for key, value in item.items()
                        if key not in {"id", "name"}
                    },
                }
            )
    except AppError:
        models = []

    if not models:
        models = [
            {
                "name": provider.default_model,
                "label": provider.default_model,
                "is_default": True,
                "details": {"fallback": True},
            }
        ]

    return {
        "provider_source": AI_SOURCE_USER_EXTERNAL,
        "provider_id": provider.id,
        "provider_key": None,
        "provider_label": provider.display_name,
        "provider_type": provider.provider_type,
        "enabled": provider.enabled,
        "models": models,
    }


def _inflate_provider_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    payload = dict(snapshot)
    encrypted_api_key = _normalize_optional_text(payload.get("api_key_encrypted"))
    if encrypted_api_key is not None:
        payload["api_key"] = decrypt_secret(encrypted_api_key)
    return payload


def _build_assessment_messages(*, finding: Finding) -> list[dict[str, str]]:
    prompt_block = _resolve_llm_prompt_block(finding)
    user_prompt = (
        "请基于以下漏洞信息进行研判，并严格返回 JSON。\n\n"
        f"{prompt_block}\n\n"
        "JSON 字段要求：\n"
        "- verdict: TP/FP/NEEDS_REVIEW\n"
        "- confidence: high/medium/low\n"
        "- summary: 字符串\n"
        "- risk_reason: 字符串\n"
        "- false_positive_signals: 字符串数组\n"
        "- fix_suggestions: 字符串数组\n"
        "- evidence_refs: 字符串数组"
    )
    return [
        {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _build_chat_messages(
    *,
    finding: Finding,
    history: list[AIChatMessage],
    latest_assessment: FindingAIAssessment | None,
) -> list[dict[str, str]]:
    prompt_block = _resolve_llm_prompt_block(finding)
    context_lines = [
        "当前漏洞上下文如下：",
        prompt_block,
    ]
    if latest_assessment is not None:
        context_lines.extend(
            [
                "",
                "最新 AI 研判结果：",
                json.dumps(latest_assessment.summary_json, ensure_ascii=False),
            ]
        )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "system", "content": "\n".join(context_lines)},
    ]
    settings = get_settings()
    recent_history = history[-max(1, int(settings.ai_chat_history_limit)) :]
    for item in recent_history:
        messages.append({"role": item.role, "content": item.content})
    return messages


def _build_general_chat_messages(
    *, history: list[AIChatMessage]
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": GENERAL_CHAT_SYSTEM_PROMPT},
    ]
    settings = get_settings()
    recent_history = history[-max(1, int(settings.ai_chat_history_limit)) :]
    for item in recent_history:
        messages.append({"role": item.role, "content": item.content})
    return messages


def _resolve_llm_prompt_block(finding: Finding) -> str:
    evidence = (
        dict(finding.evidence_json or {})
        if isinstance(finding.evidence_json, dict)
        else {}
    )
    prompt_block = _normalize_optional_text(evidence.get("llm_prompt_block"))
    if prompt_block:
        return prompt_block

    llm_payload = (
        evidence.get("llm_payload")
        if isinstance(evidence.get("llm_payload"), dict)
        else {}
    )
    if llm_payload:
        return _build_prompt_block_from_payload(llm_payload)

    location = str(finding.file_path or finding.sink_file or finding.source_file or "-")
    line = finding.line_start or finding.sink_line or finding.source_line
    trace_summary = str(evidence.get("trace_summary") or "-")
    return (
        f"Rule: {finding.rule_key}\n"
        f"Severity: {finding.severity}\n"
        f"VulnType: {finding.vuln_type or '-'}\n"
        f"Location: {location}{':' + str(line) if line else ''}\n"
        f"Trace: {trace_summary}"
    )


def _build_prompt_block_from_payload(llm_payload: dict[str, object]) -> str:
    lines = [
        f"Rule: {llm_payload.get('rule_key') or '-'}",
        f"Severity: {llm_payload.get('severity') or '-'}",
        f"VulnType: {llm_payload.get('vuln_type') or '-'}",
        f"Reason: {llm_payload.get('why_flagged') or '-'}",
        f"Trace: {llm_payload.get('trace_summary') or '-'}",
    ]
    location = (
        llm_payload.get("location")
        if isinstance(llm_payload.get("location"), dict)
        else {}
    )
    if location:
        file_path = str(location.get("file_path") or "").strip() or "-"
        line_start = _to_int(location.get("line_start"))
        lines.insert(
            3, f"Location: {file_path}{':' + str(line_start) if line_start else ''}"
        )
    return "\n".join(lines)


def _parse_assessment_content(content: str) -> dict[str, object]:
    raw = str(content or "").strip()
    candidate = raw
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        verdict = str(payload.get("verdict") or "NEEDS_REVIEW").strip().upper()
        confidence = str(payload.get("confidence") or "medium").strip().lower()
        return {
            "verdict": verdict
            if verdict in {"TP", "FP", "NEEDS_REVIEW"}
            else "NEEDS_REVIEW",
            "confidence": confidence
            if confidence in {"high", "medium", "low"}
            else "medium",
            "summary": str(payload.get("summary") or "").strip(),
            "risk_reason": str(payload.get("risk_reason") or "").strip(),
            "false_positive_signals": _string_list(
                payload.get("false_positive_signals")
            ),
            "fix_suggestions": _string_list(payload.get("fix_suggestions")),
            "evidence_refs": _string_list(payload.get("evidence_refs")),
        }
    return {
        "verdict": "NEEDS_REVIEW",
        "confidence": "medium",
        "summary": _truncate_text(raw, 4000),
        "risk_reason": "模型未返回结构化 JSON，已保留原始文本供人工复核。",
        "false_positive_signals": [],
        "fix_suggestions": [],
        "evidence_refs": [],
    }


def _fail_ai_job(
    db: Session, *, job_id: uuid.UUID, failure_code: str, failure_message: str
) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    if job.status in TERMINAL_JOB_STATUSES:
        return
    job.status = JobStatus.FAILED.value
    job.stage = JobStage.AI.value
    job.failure_code = failure_code
    job.failure_stage = job.stage
    job.failure_category = "AI"
    job.failure_hint = failure_message
    job.finished_at = utc_now()
    _append_ai_log(
        job_id=job.id,
        stage=job.stage,
        message=f"AI 任务失败: code={failure_code}, message={failure_message}",
        project_id=job.project_id,
        db=db,
    )
    append_audit_log(
        db,
        request_id=str((job.payload or {}).get("request_id") or ""),
        operator_user_id=job.created_by,
        action="ai.job.failed",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        result="FAILED",
        error_code=failure_code,
        detail_json={"message": failure_message},
    )
    db.commit()


def _append_ai_log(
    *,
    job_id: uuid.UUID,
    stage: str,
    message: str,
    project_id: uuid.UUID | None,
    db: Session,
) -> None:
    append_task_log(
        task_type=TaskLogType.AI.value,
        task_id=job_id,
        stage=stage,
        message=message,
        project_id=project_id,
        db=db,
    )


def _set_ai_job_running(db: Session, *, job: Job, stage: str) -> None:
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.stage = stage
    job.status = JobStatus.RUNNING.value
    db.flush()


def _set_ai_step_status(
    db: Session, *, job_id: uuid.UUID, step_key: str, status: str
) -> None:
    step = db.scalar(
        select(JobStep).where(JobStep.job_id == job_id, JobStep.step_key == step_key)
    )
    if step is None:
        raise AppError(
            code="NOT_FOUND",
            status_code=404,
            message="AI 任务步骤不存在",
            detail={"job_id": str(job_id), "step_key": step_key},
        )
    timestamp = utc_now()
    step.status = status
    if status == JobStepStatus.PENDING.value:
        step.started_at = None
        step.finished_at = None
        step.duration_ms = None
    elif status == JobStepStatus.RUNNING.value:
        if step.started_at is None:
            step.started_at = timestamp
        step.finished_at = None
        step.duration_ms = None
    elif status in TERMINAL_STEP_STATUSES:
        if step.started_at is None:
            step.started_at = timestamp
        step.finished_at = timestamp
        step.duration_ms = _duration_ms_between(step.started_at, step.finished_at)
    db.flush()


def _unset_other_user_defaults(
    db: Session, *, user_id: uuid.UUID, provider_id: uuid.UUID
) -> None:
    rows = db.scalars(
        select(UserAIProvider).where(
            UserAIProvider.user_id == user_id,
            UserAIProvider.id != provider_id,
            UserAIProvider.is_default.is_(True),
        )
    ).all()
    for row in rows:
        row.is_default = False
    db.flush()


def _normalize_url(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="base_url")
    return normalized.rstrip("/")


def _normalize_optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_required_text(value: object, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message=f"{field_name} 不能为空",
            detail={"field": field_name},
        )
    return normalized


def _normalize_model_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = str(raw or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _candidate_ollama_urls(primary_url: str | None) -> list[str]:
    candidates = [
        _normalize_optional_text(primary_url),
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://ollama:11434",
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = candidate.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _first_published_model(provider: SystemAIProvider) -> str | None:
    models = _normalize_model_list(provider.published_models_json)
    return models[0] if models else None


def _safe_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized:
            items.append(normalized)
    return items


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max(0, max_length - 1)] + "..."


def _duration_ms_between(start: datetime, end: datetime) -> int:
    normalized_start = start
    normalized_end = end
    if normalized_start.tzinfo is None and normalized_end.tzinfo is not None:
        normalized_end = normalized_end.replace(tzinfo=None)
    elif normalized_start.tzinfo is not None and normalized_end.tzinfo is None:
        normalized_start = normalized_start.replace(tzinfo=None)
    return max(0, int((normalized_end - normalized_start).total_seconds() * 1000))
