from __future__ import annotations

import json
import re
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
    FindingPath,
    FindingPathEdge,
    FindingPathStep,
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
from app.services.path_graph_service import edge_display_label
from app.services.rule_file_service import get_rules_by_keys
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
    "你是代码安全研判助手。请只基于给定证据、数据传播链路和代码上下文进行判断，"
    "不要臆造未提供的信息。你的输出必须是单个 JSON object，禁止输出 Markdown、代码块、"
    "前后解释文字或多余字段。JSON 字段固定为 schema_version, verdict, confidence, summary,"
    " risk_reason, false_positive_signals, fix_suggestions, evidence_refs。"
    "schema_version 固定为 codescope.ai_assessment.v1；verdict 只能是 TP、FP、NEEDS_REVIEW 之一；"
    "confidence 只能是 high、medium、low 之一。"
)

ASSESSMENT_RESPONSE_SCHEMA_VERSION = "codescope.ai_assessment.v1"
ASSESSMENT_JSON_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "schema_version": ("schema_version", "schemaVersion", "version"),
    "verdict": ("verdict", "decision", "conclusion", "result", "判定", "结论"),
    "confidence": ("confidence", "certainty", "置信度", "可信度"),
    "summary": ("summary", "摘要", "结论摘要", "overview"),
    "risk_reason": (
        "risk_reason",
        "riskReason",
        "risk reason",
        "reason",
        "风险依据",
        "原因分析",
    ),
    "false_positive_signals": (
        "false_positive_signals",
        "falsePositiveSignals",
        "false positive signals",
        "fp_signals",
        "误报线索",
    ),
    "fix_suggestions": (
        "fix_suggestions",
        "fixSuggestions",
        "fix suggestions",
        "remediation",
        "修复建议",
    ),
    "evidence_refs": (
        "evidence_refs",
        "evidenceRefs",
        "evidence refs",
        "evidence",
        "证据引用",
    ),
}

ASSESSMENT_PROFILE_HINTS: dict[str, str] = {
    "GENERIC": (
        "优先判断命中原因是否真的形成可利用风险；如果证据链存在断点、关键控制条件缺失、"
        "或上下文不足，应偏向 NEEDS_REVIEW，而不是臆断。"
    ),
    "XSS": (
        "重点检查输入是否真正流入可执行的 HTML/JS/模板输出位置，结合输出上下文、模板默认转义、"
        "显式编码/过滤、前端框架自动 escaping 判断是否可利用。"
    ),
    "SQLI": (
        "重点检查参数是否可控、是否进入 SQL 拼接或动态片段、ORM/预编译占位符是否有效拦截，"
        "不要把普通参数绑定误判为 SQL 注入。"
    ),
    "SSRF": (
        "重点检查用户输入是否控制目标 URL/host/path/protocol，是否存在内网访问、元数据访问、"
        "协议白名单和 host 校验等有效限制。"
    ),
    "DESERIALIZATION": (
        "重点检查不可信数据是否进入反序列化入口，是否存在可达 gadget 链、危险 autoType/白名单缺失、"
        "以及真实触发条件，不要只因出现相关 API 就直接判定高危。"
    ),
    "CMDI": (
        "重点检查用户输入是否进入命令拼接、shell 解释器或 ProcessBuilder 等执行入口，"
        "以及参数化执行、固定命令模板、白名单过滤是否足以阻断命令注入。"
    ),
    "CODEI": (
        "重点检查表达式、脚本或反射执行入口是否被外部输入控制，关注 OGNL、SpEL、MVEL、"
        "ScriptEngine 等解释执行能力以及是否存在安全沙箱。"
    ),
    "SSTI": (
        "重点检查模板名或模板变量是否可控，模板引擎是否支持表达式求值、危险对象访问、"
        "以及模板上下文是否暴露高危能力。"
    ),
    "XXE": (
        "重点检查 XML 解析是否允许外部实体、DTD、XInclude 或外部资源访问，结合解析器配置判断是否可利用。"
    ),
    "PATHTRAVERSAL": (
        "重点检查用户输入是否控制文件路径、目录拼接或下载读取目标，路径规范化、根目录限制、"
        "白名单校验是否真正生效。"
    ),
    "UPLOAD": (
        "重点检查上传后是否可被执行或覆盖敏感位置，关注文件名、路径、类型校验、存储位置、"
        "URL 暴露和后续处理逻辑。"
    ),
    "REDIRECT": (
        "重点检查跳转目标是否被外部输入控制，是否限制站内跳转、白名单域名或协议，"
        "不要把固定路由跳转误判为开放重定向。"
    ),
    "INFOLEAK": (
        "重点检查敏感信息是否真实对外暴露，关注错误信息、调试接口、配置泄露、凭据明文、"
        "以及是否仅在开发环境或受限边界内可见。"
    ),
}

ASSESSMENT_RULE_HINTS: tuple[tuple[str, str], ...] = (
    (
        "fastjson",
        "针对 Fastjson 规则，重点判断 autoType、白名单、版本修复状态以及输入是否真正进入 parse/反序列化链路。",
    ),
    (
        "jndi",
        "针对 JNDI 相关规则，重点判断外部输入是否可控地触发远程查找、协议限制、以及上下游是否已禁用远程加载。",
    ),
    (
        "mybatis",
        "针对 MyBatis 相关规则，重点判断是否存在 ${} 直接拼接、动态 order by/table 名拼接，而不是普通 #{} 参数绑定。",
    ),
)

CHAT_SYSTEM_PROMPT = (
    "你是代码安全分析助手。回答时仅基于当前漏洞证据、代码上下文、历史 AI 研判和用户问题。"
    "如果证据不足，明确说明需要更多上下文"
)

GENERAL_CHAT_SYSTEM_PROMPT = (
    "你是代码安全与工程辅助助手。可以直接和用户讨论代码、安全、架构、漏洞修复、"
    "模型能力等话题。回答时保持专业、准确、简洁；如果缺少上下文，明确指出需要补充信息。"
)


@dataclass(slots=True)
class AssessmentRunResult:
    assessment: FindingAIAssessment
    ok: bool


@dataclass(slots=True)
class AssessmentPromptBundle:
    messages: list[dict[str, str]]
    budget_meta: dict[str, object]
    context_payload: dict[str, object]


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
    snapshot = _prepare_assessment_provider_snapshot(
        _inflate_provider_snapshot(provider_snapshot)
    )
    prompt_bundle = _build_assessment_messages(
        db,
        finding=finding,
        provider_snapshot=snapshot,
    )
    result = run_provider_chat(
        provider_snapshot=snapshot, messages=prompt_bundle.messages
    )
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
    assessment.summary_json = {**summary, "prompt_meta": prompt_bundle.budget_meta}
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
    settings = get_settings()
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
        "max_context_tokens": int(settings.ai_default_max_context_tokens),
        "max_output_tokens": int(settings.ai_reserved_output_tokens),
    }


def _build_user_provider_snapshot(
    *, provider: UserAIProvider, override_model: str | None
) -> dict[str, object]:
    settings = get_settings()
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
        "max_context_tokens": int(settings.ai_default_max_context_tokens),
        "max_output_tokens": int(settings.ai_reserved_output_tokens),
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


def _build_assessment_messages(
    db: Session,
    *,
    finding: Finding,
    provider_snapshot: dict[str, object],
) -> AssessmentPromptBundle:
    context_payload = _build_assessment_context_payload(db, finding=finding)
    prompt_context = json.loads(json.dumps(context_payload, ensure_ascii=False))
    prompt_hint_meta = _resolve_assessment_prompt_hint(context_payload=prompt_context)
    budget_meta = _build_assessment_budget(provider_snapshot=provider_snapshot)

    system_prompt = (
        f"{ASSESSMENT_SYSTEM_PROMPT}\n漏洞专项关注点：{prompt_hint_meta['hint']}"
    )
    user_prompt, budget_meta = _render_assessment_user_prompt(
        context_payload=prompt_context,
        budget_meta={
            **budget_meta,
            "profile": prompt_hint_meta["profile"],
            "rule_hint_applied": bool(prompt_hint_meta["rule_hint"]),
        },
    )
    return AssessmentPromptBundle(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        budget_meta=budget_meta,
        context_payload=prompt_context,
    )


def _prepare_assessment_provider_snapshot(
    provider_snapshot: dict[str, object],
) -> dict[str, object]:
    payload = dict(provider_snapshot)
    settings = get_settings()
    max_context_tokens = _to_int(payload.get("max_context_tokens")) or int(
        settings.ai_default_max_context_tokens
    )
    max_output_tokens = _to_int(payload.get("max_output_tokens")) or int(
        settings.ai_reserved_output_tokens
    )
    payload["max_context_tokens"] = max(2048, max_context_tokens)
    payload["max_output_tokens"] = max(512, min(max_output_tokens, max_context_tokens))
    return payload


def _build_assessment_context_payload(
    db: Session, *, finding: Finding
) -> dict[str, object]:
    evidence = (
        dict(finding.evidence_json or {})
        if isinstance(finding.evidence_json, dict)
        else {}
    )
    llm_payload = (
        dict(evidence.get("llm_payload"))
        if isinstance(evidence.get("llm_payload"), dict)
        else {}
    )
    rule_meta = get_rules_by_keys({finding.rule_key}).get(finding.rule_key)
    path_payload = _build_assessment_path_payload(db, finding=finding)

    reason = _normalize_optional_text(llm_payload.get("why_flagged"))
    trace_summary = _normalize_optional_text(llm_payload.get("trace_summary"))
    key_path_summary = _normalize_optional_text(path_payload.get("key_path_summary"))

    core_location = (
        llm_payload.get("location")
        if isinstance(llm_payload.get("location"), dict)
        else {}
    )
    source = (
        llm_payload.get("source") if isinstance(llm_payload.get("source"), dict) else {}
    )
    sink = llm_payload.get("sink") if isinstance(llm_payload.get("sink"), dict) else {}

    code_context = (
        llm_payload.get("code_context")
        if isinstance(llm_payload.get("code_context"), dict)
        else {}
    )

    return {
        "finding_core": {
            "rule_key": finding.rule_key,
            "rule_name": rule_meta.name if rule_meta is not None else finding.rule_key,
            "rule_description": (
                _normalize_optional_text(rule_meta.description) if rule_meta else None
            ),
            "severity": finding.severity,
            "vuln_type": finding.vuln_type
            or (rule_meta.vuln_type if rule_meta else None),
            "location": _sanitize_location_payload(core_location, finding=finding),
            "source": _sanitize_endpoint_payload(
                source,
                fallback_file=finding.source_file,
                fallback_line=finding.source_line,
            ),
            "sink": _sanitize_endpoint_payload(
                sink, fallback_file=finding.sink_file, fallback_line=finding.sink_line
            ),
        },
        "analysis_focus": {
            "why_flagged": reason,
            "trace_summary": trace_summary,
            "key_path_summary": key_path_summary or trace_summary,
            "data_flow_chain": path_payload.get("data_flow_chain")
            if isinstance(path_payload.get("data_flow_chain"), list)
            else [],
        },
        "evidence_preview": _string_list(llm_payload.get("evidence_preview")),
        "code_context": _sanitize_code_context_payload(code_context),
    }


def _build_assessment_path_payload(
    db: Session, *, finding: Finding
) -> dict[str, object]:
    row = db.scalar(
        select(FindingPath)
        .where(FindingPath.finding_id == finding.id)
        .order_by(FindingPath.path_length.asc(), FindingPath.path_order.asc())
        .limit(1)
    )
    if row is None:
        return {}

    step_rows = db.scalars(
        select(FindingPathStep)
        .where(FindingPathStep.finding_path_id == row.id)
        .order_by(FindingPathStep.step_order.asc())
    ).all()
    edge_rows = db.scalars(
        select(FindingPathEdge)
        .where(FindingPathEdge.finding_path_id == row.id)
        .order_by(FindingPathEdge.edge_order.asc())
    ).all()
    if not step_rows:
        return {}

    chain = _build_data_flow_chain(step_rows=step_rows, edge_rows=edge_rows)
    return {
        "path_length": row.path_length,
        "key_path_summary": _build_data_flow_summary(chain),
        "data_flow_chain": chain,
    }


def _build_data_flow_chain(
    *,
    step_rows: list[FindingPathStep],
    edge_rows: list[FindingPathEdge],
) -> list[dict[str, object]]:
    if not step_rows:
        return []
    edge_by_order = {int(edge.edge_order): edge for edge in edge_rows}
    selected_indexes = _select_key_flow_indexes(
        step_rows=step_rows, edge_by_order=edge_by_order
    )

    chain: list[dict[str, object]] = []
    for selected_index in selected_indexes:
        step = step_rows[selected_index]
        next_selected_index = _next_selected_index(selected_indexes, selected_index)
        edge_label = None
        if next_selected_index is not None:
            for edge_index in range(selected_index, next_selected_index):
                edge = edge_by_order.get(edge_index)
                if edge is not None:
                    edge_label = edge_display_label(edge.edge_type)
                    break
        chain.append(
            {
                "step_order": step.step_order,
                "location": _format_location(step.file_path, step.line_no),
                "display_name": _truncate_text(
                    str(
                        step.display_name
                        or step.symbol_name
                        or step.owner_method
                        or "-"
                    ).strip()
                    or "-",
                    160,
                ),
                "node_kind": _normalize_optional_text(step.node_kind),
                "code_snippet": _normalize_optional_text(step.code_snippet),
                "edge_to_next": edge_label,
            }
        )
    return chain


def _select_key_flow_indexes(
    *,
    step_rows: list[FindingPathStep],
    edge_by_order: dict[int, FindingPathEdge],
) -> list[int]:
    settings = get_settings()
    limit = max(2, int(settings.ai_assessment_max_flow_steps))
    total = len(step_rows)
    if total <= limit:
        return list(range(total))

    keep = {0, total - 1}
    for index in range(1, total - 1):
        prev_step = step_rows[index - 1]
        current = step_rows[index]
        edge = edge_by_order.get(index - 1)
        if edge is not None and edge.edge_type in {
            "REF",
            "PARAM_PASS",
            "SRC_FLOW",
            "CALLS",
            "ARG",
        }:
            keep.add(index)
            continue
        if (current.file_path or "") != (prev_step.file_path or ""):
            keep.add(index)
            continue
        if (current.owner_method or "") != (prev_step.owner_method or ""):
            keep.add(index)

    ordered = sorted(keep)
    if len(ordered) <= limit:
        return ordered

    middle = ordered[1:-1]
    slots = max(0, limit - 2)
    if len(middle) <= slots:
        return ordered[:1] + middle + ordered[-1:]
    picked = [
        middle[int(round(index * (len(middle) - 1) / max(1, slots - 1)))]
        for index in range(slots)
    ]
    return [ordered[0], *sorted(set(picked)), ordered[-1]]


def _next_selected_index(selected_indexes: list[int], current_index: int) -> int | None:
    for value in selected_indexes:
        if value > current_index:
            return value
    return None


def _build_data_flow_summary(chain: list[dict[str, object]]) -> str | None:
    if not chain:
        return None
    parts: list[str] = []
    for index, item in enumerate(chain):
        location = str(item.get("location") or "-")
        display_name = str(item.get("display_name") or "-")
        parts.append(f"{index + 1}. {display_name} @ {location}")
        edge_label = str(item.get("edge_to_next") or "").strip()
        if edge_label:
            parts.append(f" --[{edge_label}]--> ")
    return _truncate_text("".join(parts), 1600)


def _format_location(file_path: str | None, line_no: int | None) -> str:
    normalized_path = str(file_path or "").strip() or "-"
    if line_no is None:
        return normalized_path
    return f"{normalized_path}:{line_no}"


def _sanitize_location_payload(
    payload: dict[str, object],
    *,
    finding: Finding,
) -> dict[str, object]:
    return {
        "file_path": _normalize_optional_text(payload.get("file_path"))
        or finding.file_path
        or finding.sink_file
        or finding.source_file,
        "line_start": _to_int(payload.get("line_start"))
        or finding.line_start
        or finding.sink_line
        or finding.source_line,
        "line_end": _to_int(payload.get("line_end")) or finding.line_end,
    }


def _sanitize_endpoint_payload(
    payload: dict[str, object],
    *,
    fallback_file: str | None,
    fallback_line: int | None,
) -> dict[str, object]:
    return {
        "file": _normalize_optional_text(payload.get("file")) or fallback_file,
        "line": _to_int(payload.get("line")) or fallback_line,
    }


def _sanitize_code_context_payload(payload: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key in ("focus", "source", "sink"):
        value = _normalize_optional_text(payload.get(key))
        if value:
            normalized[key] = value
    return normalized


def _resolve_assessment_prompt_hint(
    *, context_payload: dict[str, object]
) -> dict[str, str]:
    finding_core = (
        context_payload.get("finding_core")
        if isinstance(context_payload.get("finding_core"), dict)
        else {}
    )
    vuln_type = str(finding_core.get("vuln_type") or "").strip().upper()
    rule_key = str(finding_core.get("rule_key") or "").strip().lower()
    profile = _resolve_assessment_profile_key(vuln_type=vuln_type, rule_key=rule_key)
    rule_hint = next(
        (hint for token, hint in ASSESSMENT_RULE_HINTS if token and token in rule_key),
        "",
    )
    hints = [
        ASSESSMENT_PROFILE_HINTS.get(profile) or ASSESSMENT_PROFILE_HINTS["GENERIC"]
    ]
    if rule_hint:
        hints.append(rule_hint)
    return {
        "profile": profile,
        "rule_hint": rule_hint,
        "hint": " ".join(item for item in hints if item).strip(),
    }


def _resolve_assessment_profile_key(*, vuln_type: str, rule_key: str) -> str:
    aliases = {
        "OPEN_REDIRECT": "REDIRECT",
        "URLREDIRECT": "REDIRECT",
        "PATH_TRAVERSAL": "PATHTRAVERSAL",
        "FILE_UPLOAD": "UPLOAD",
        "RCE": "CODEI",
        "INFO_LEAK": "INFOLEAK",
    }
    normalized = aliases.get(vuln_type, vuln_type)
    if normalized in ASSESSMENT_PROFILE_HINTS:
        return normalized
    for token, profile in (
        ("deserialization", "DESERIALIZATION"),
        ("sqli", "SQLI"),
        ("xss", "XSS"),
        ("ssrf", "SSRF"),
        ("xxe", "XXE"),
        ("cmdi", "CMDI"),
        ("codei", "CODEI"),
        ("ssti", "SSTI"),
        ("pathtraver", "PATHTRAVERSAL"),
        ("upload", "UPLOAD"),
        ("redirect", "REDIRECT"),
        ("infoleak", "INFOLEAK"),
    ):
        if token in rule_key:
            return profile
    return "GENERIC"


def _build_assessment_budget(
    *, provider_snapshot: dict[str, object]
) -> dict[str, object]:
    settings = get_settings()
    max_context_tokens = _to_int(provider_snapshot.get("max_context_tokens")) or int(
        settings.ai_default_max_context_tokens
    )
    reserved_output_tokens = _to_int(provider_snapshot.get("max_output_tokens")) or int(
        settings.ai_reserved_output_tokens
    )
    reserved_system_tokens = int(settings.ai_reserved_system_tokens)
    safety_margin_tokens = int(settings.ai_context_safety_margin_tokens)
    max_input_tokens = max(
        2048,
        max_context_tokens
        - reserved_output_tokens
        - reserved_system_tokens
        - safety_margin_tokens,
    )
    return {
        "max_context_tokens": max_context_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "reserved_system_tokens": reserved_system_tokens,
        "safety_margin_tokens": safety_margin_tokens,
        "max_input_tokens": max_input_tokens,
    }


def _render_assessment_user_prompt(
    *,
    context_payload: dict[str, object],
    budget_meta: dict[str, object],
) -> tuple[str, dict[str, object]]:
    prompt = _render_assessment_prompt_text(context_payload)
    input_tokens = _estimate_text_tokens(prompt)
    while input_tokens > int(budget_meta["max_input_tokens"]):
        changed = _shrink_assessment_context_payload(context_payload)
        if not changed:
            break
        prompt = _render_assessment_prompt_text(context_payload)
        input_tokens = _estimate_text_tokens(prompt)
    return prompt, {
        **budget_meta,
        "input_tokens_estimate": input_tokens,
        "input_chars": len(prompt),
    }


def _render_assessment_prompt_text(context_payload: dict[str, object]) -> str:
    schema_payload = {
        "schema_version": ASSESSMENT_RESPONSE_SCHEMA_VERSION,
        "verdict": "TP|FP|NEEDS_REVIEW",
        "confidence": "high|medium|low",
        "summary": "string",
        "risk_reason": "string",
        "false_positive_signals": ["string"],
        "fix_suggestions": ["string"],
        "evidence_refs": ["string"],
    }
    context_json = json.dumps(
        context_payload, ensure_ascii=False, separators=(",", ":")
    )
    schema_json = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":"))
    return (
        "请基于以下结构化漏洞上下文进行安全研判。只允许依据输入证据判断。\n"
        "如果证据无法形成完整利用链，请输出 NEEDS_REVIEW 或 FP，不要臆造缺失前提。\n"
        f"输出 JSON Schema: {schema_json}\n"
        f"漏洞上下文(JSON): {context_json}"
    )


def _shrink_assessment_context_payload(context_payload: dict[str, object]) -> bool:
    for section_key in ("code_context", "evidence_preview", "analysis_focus"):
        section = context_payload.get(section_key)
        if section_key == "code_context" and isinstance(section, dict):
            for key in ("sink", "source", "focus"):
                value = _normalize_optional_text(section.get(key))
                if value and len(value) > 120:
                    section[key] = _truncate_text(value, max(120, len(value) // 2))
                    return True
                if value:
                    section.pop(key, None)
                    return True
        if section_key == "evidence_preview" and isinstance(section, list) and section:
            section.pop()
            return True
        if section_key == "analysis_focus" and isinstance(section, dict):
            chain = section.get("data_flow_chain")
            if isinstance(chain, list) and len(chain) > 3:
                section["data_flow_chain"] = chain[:-1]
                section["key_path_summary"] = _build_data_flow_summary(
                    section["data_flow_chain"]
                )
                return True
            for key in ("trace_summary", "key_path_summary", "why_flagged"):
                value = _normalize_optional_text(section.get(key))
                if value and len(value) > 160:
                    section[key] = _truncate_text(value, max(160, len(value) // 2))
                    return True
    return False


def _estimate_text_tokens(text: str) -> int:
    raw = str(text or "")
    if not raw:
        return 0
    cjk_count = sum(1 for char in raw if "\u4e00" <= char <= "\u9fff")
    other_chars = max(0, len(raw) - cjk_count)
    return cjk_count + ((other_chars + 2) // 3)


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
    for candidate in _assessment_json_candidates(raw):
        try:
            payload = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return _normalize_assessment_payload(payload, fallback_text=raw)

    fallback_payload = _parse_assessment_labeled_text(raw)
    if fallback_payload is not None:
        return _normalize_assessment_payload(fallback_payload, fallback_text=raw)

    return {
        "schema_version": ASSESSMENT_RESPONSE_SCHEMA_VERSION,
        "verdict": "NEEDS_REVIEW",
        "confidence": "medium",
        "summary": _truncate_text(raw, 4000),
        "risk_reason": "模型未返回结构化 JSON，已保留原始文本供人工复核。",
        "false_positive_signals": [],
        "fix_suggestions": [],
        "evidence_refs": [],
    }


def _assessment_json_candidates(raw: str) -> list[str]:
    candidates: list[str] = []
    stripped = raw.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            candidates.append("\n".join(lines[1:-1]).strip())
    candidates.append(stripped)

    start = stripped.find("{")
    while start >= 0:
        depth = 0
        for index in range(start, len(stripped)):
            char = stripped[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(stripped[start : index + 1])
                    break
        start = stripped.find("{", start + 1)

    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _normalize_assessment_payload(
    payload: dict[str, object], *, fallback_text: str
) -> dict[str, object]:
    candidate = payload
    for key in ("assessment", "result", "data"):
        inner = candidate.get(key)
        if isinstance(inner, dict):
            candidate = inner
            break

    verdict = (
        str(_get_assessment_value(candidate, "verdict") or "NEEDS_REVIEW")
        .strip()
        .upper()
    )
    confidence = (
        str(_get_assessment_value(candidate, "confidence") or "medium").strip().lower()
    )
    summary = _normalize_optional_text(_get_assessment_value(candidate, "summary"))
    risk_reason = _normalize_optional_text(
        _get_assessment_value(candidate, "risk_reason")
    )

    return {
        "schema_version": ASSESSMENT_RESPONSE_SCHEMA_VERSION,
        "verdict": verdict
        if verdict in {"TP", "FP", "NEEDS_REVIEW"}
        else "NEEDS_REVIEW",
        "confidence": confidence
        if confidence in {"high", "medium", "low"}
        else "medium",
        "summary": summary or _truncate_text(fallback_text, 4000),
        "risk_reason": risk_reason
        or "模型未完整返回风险依据，已保留原始文本供人工复核。",
        "false_positive_signals": _string_list(
            _get_assessment_value(candidate, "false_positive_signals")
        ),
        "fix_suggestions": _string_list(
            _get_assessment_value(candidate, "fix_suggestions")
        ),
        "evidence_refs": _string_list(
            _get_assessment_value(candidate, "evidence_refs")
        ),
    }


def _get_assessment_value(payload: dict[str, object], field: str) -> object:
    aliases = ASSESSMENT_JSON_FIELD_ALIASES.get(field, (field,))
    for key in aliases:
        if key in payload:
            return payload.get(key)
    return None


def _parse_assessment_labeled_text(raw: str) -> dict[str, object] | None:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return None

    alias_to_field: dict[str, str] = {}
    for field, aliases in ASSESSMENT_JSON_FIELD_ALIASES.items():
        for alias in aliases:
            alias_to_field[alias.lower()] = field

    payload: dict[str, object] = {}
    current_field: str | None = None
    buffered: list[str] = []

    def flush_current() -> None:
        nonlocal buffered, current_field
        if current_field is None:
            buffered = []
            return
        text = "\n".join(buffered).strip()
        if current_field in {
            "false_positive_signals",
            "fix_suggestions",
            "evidence_refs",
        }:
            payload[current_field] = _string_list(text)
        elif text:
            payload[current_field] = text
        current_field = None
        buffered = []

    for raw_line in lines:
        line = raw_line.lstrip("-*0123456789. ").strip()
        matched_field = None
        matched_value = ""
        for alias, field in alias_to_field.items():
            pattern = rf"^{re.escape(alias)}\s*[:：]\s*(.*)$"
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                matched_field = field
                matched_value = match.group(1).strip()
                break
        if matched_field is not None:
            flush_current()
            current_field = matched_field
            if matched_value:
                buffered.append(matched_value)
            continue
        if current_field is not None:
            buffered.append(line)

    flush_current()

    verdict_match = re.search(r"\b(TP|FP|NEEDS_REVIEW)\b", raw, flags=re.IGNORECASE)
    if verdict_match and "verdict" not in payload:
        payload["verdict"] = verdict_match.group(1).upper()
    confidence_match = re.search(r"\b(high|medium|low)\b", raw, flags=re.IGNORECASE)
    if confidence_match and "confidence" not in payload:
        payload["confidence"] = confidence_match.group(1).lower()

    if not payload:
        return None
    return payload


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
    if isinstance(value, str):
        parts = [
            item.strip(" -*\t")
            for item in re.split(r"[\n,;；]+", value)
            if item.strip(" -*\t")
        ]
        return parts
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
