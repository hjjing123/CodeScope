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
)
from app.services.assessment_context_service import (
    build_assessment_extraction,
    resolve_assessment_profile,
)
from app.services.audit_service import append_audit_log
from app.services.path_graph_service import edge_display_label
from app.services.rule_file_service import get_rules_by_keys
from app.services.task_log_service import append_task_log


SYSTEM_OLLAMA_PROVIDER_KEY = "system_ollama"
AI_SOURCE_SYSTEM_OLLAMA = "system_ollama"
AI_SOURCE_USER_EXTERNAL = "user_external"
AI_CHAT_SESSION_SEED_ASSESSMENT = "assessment_review"
MODEL_VERIFICATION_PROMPT = "Reply with exactly OK."
MODEL_VERIFICATION_MAX_OUTPUT_TOKENS = 16

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
    "JNDII": (
        "重点检查 JNDI lookup 参数是否可控、是否限制协议或命名空间，"
        "以及运行时是否已禁用远程代码库加载。"
    ),
    "LDAPI": (
        "重点检查 LDAP filter 或查询条件是否由外部输入拼接，是否做特殊字符转义、"
        "搜索基准限制与权限隔离。"
    ),
    "HPE": (
        "重点检查资源访问是否同时包含用户或租户约束，以及是否存在显式权限校验，"
        "不要把仅有身份认证误判为通过授权。"
    ),
    "CORS": (
        "重点检查是否反射或通配 Origin、是否允许凭证、以及策略是否应用在敏感接口上，"
        "不要忽略代理层和环境差异。"
    ),
    "MISCONFIG": (
        "重点检查危险配置是否在生产环境真实生效，是否受鉴权、IP 白名单或网关限制，"
        "不要只凭配置项命中就直接判定可利用。"
    ),
    "INFOLEAK": (
        "重点检查敏感信息是否真实对外暴露，关注错误信息、调试接口、配置泄露、凭据明文、"
        "以及是否仅在开发环境或受限边界内可见。"
    ),
    "HARDCODE_SECRET": (
        "重点检查命中字面量是否为真实凭据、是否进入运行时代码与生产构建，"
        "以及是否可以通过环境变量或密钥中心替换。"
    ),
    "WEAK_PASSWORD": (
        "重点检查弱口令是否对应默认账号或生产环境配置，是否能被 profile、环境变量或"
        "部署参数覆盖。"
    ),
    "WEAK_HASH": (
        "重点检查 MD5/SHA-1 等弱哈希的用途，区分密码、签名等安全关键场景与"
        "仅用于兼容性或非安全校验的场景。"
    ),
    "COOKIE_FLAGS": (
        "重点检查敏感 Cookie 是否设置 HttpOnly、Secure、SameSite，"
        "以及是否仅在 HTTPS 场景下发送。"
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
    display_name: str | None,
    vendor_name: str,
    base_url: str,
    api_key: str,
    default_model: str,
    timeout_seconds: int,
    temperature: float,
    enabled: bool,
    is_default: bool,
) -> UserAIProvider:
    normalized_default_model = _normalize_required_text(
        default_model, field_name="default_model"
    )
    provider = UserAIProvider(
        user_id=user_id,
        display_name=_resolve_user_provider_display_name(
            display_name=display_name,
            default_model=normalized_default_model,
        ),
        vendor_name=_normalize_required_text(vendor_name, field_name="vendor_name"),
        provider_type=AIProviderType.OPENAI_COMPATIBLE.value,
        base_url=_normalize_url(base_url),
        api_key_encrypted=encrypt_secret(api_key),
        default_model=normalized_default_model,
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
    normalized_default_model: str | None = None
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
        normalized_default_model = _normalize_required_text(
            default_model, field_name="default_model"
        )
        provider.default_model = normalized_default_model
        if display_name is None:
            provider.display_name = normalized_default_model
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
    deleted_name = _normalize_optional_text(result.get("name")) or normalized_name
    deleted_name_keys = {
        _canonicalize_ollama_model_name(normalized_name),
        _canonicalize_ollama_model_name(deleted_name),
    }
    provider.published_models_json = [
        item
        for item in _normalize_model_list(provider.published_models_json)
        if _canonicalize_ollama_model_name(item) not in deleted_name_keys
    ]
    if provider.default_model and (
        _canonicalize_ollama_model_name(provider.default_model) in deleted_name_keys
    ):
        provider.default_model = (
            provider.published_models_json[0]
            if provider.published_models_json
            else None
        )
    db.flush()
    return result


def test_user_ai_provider(provider: UserAIProvider) -> dict[str, object]:
    probe_result = _probe_user_ai_provider(
        vendor_name=provider.vendor_name,
        provider_label=provider.display_name,
        base_url=provider.base_url,
        api_key=decrypt_secret(provider.api_key_encrypted),
        timeout_seconds=int(provider.timeout_seconds),
        selected_model=provider.default_model,
        verify_selected_model=bool(provider.default_model),
    )
    selected_model_verification = probe_result.get("selected_model_verification")
    detail = {
        "base_url": probe_result.get("base_url"),
        "vendor_name": probe_result.get("vendor_name"),
        "connection_ok": bool(probe_result.get("connection_ok")),
        "model_catalog_ok": bool(probe_result.get("model_catalog_ok")),
        "allow_manual_model_input": bool(probe_result.get("allow_manual_model_input")),
        "model_count": int(probe_result.get("model_count") or 0),
        "status_label": probe_result.get("status_label"),
        "status_reason": probe_result.get("status_reason"),
        "models": probe_result.get("models") or [],
        "selected_model_verification": selected_model_verification,
    }
    return {
        "ok": bool(probe_result.get("ok")),
        "provider_type": provider.provider_type,
        "provider_label": provider.display_name,
        "detail": detail,
    }


def probe_user_ai_provider_draft(
    db: Session,
    *,
    user_id: uuid.UUID,
    vendor_name: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    selected_model: str | None = None,
    verify_selected_model: bool = False,
) -> dict[str, object]:
    del db, user_id
    return _probe_user_ai_provider(
        vendor_name=vendor_name,
        provider_label=vendor_name,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        selected_model=selected_model,
        verify_selected_model=verify_selected_model,
    )


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
    if isinstance(system_ollama, dict) and (
        bool(system_ollama.get("available"))
        or bool(_normalize_model_list(system_ollama.get("published_models")))
        or system_ollama.get("connection_ok") is not None
    ):
        items.append(_build_system_model_catalog_item(system_ollama))

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
    validated_model = validate_scan_ai_selection(
        db,
        user_id=user_id,
        ai_source=str(snapshot.get("source") or ""),
        ai_provider_id=ai_provider_id,
        ai_model=_normalize_optional_text(snapshot.get("model")),
    )
    snapshot["model"] = validated_model
    return {
        "enabled": True,
        "mode": "post_scan_enrichment",
        "source": snapshot["source"],
        "provider_snapshot": snapshot,
    }


def validate_scan_ai_selection(
    db: Session,
    *,
    user_id: uuid.UUID,
    ai_source: str | None,
    ai_provider_id: uuid.UUID | None,
    ai_model: str | None,
) -> str:
    normalized_source = _normalize_optional_text(ai_source)
    normalized_model = _normalize_optional_text(ai_model)

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
        published_models = _normalize_model_list(provider.published_models_json)
        selected_model = (
            normalized_model
            or provider.default_model
            or _first_published_model(provider)
        )
        if selected_model is None:
            raise AppError(
                code="AI_MODEL_NOT_AVAILABLE",
                status_code=422,
                message="系统 Ollama 没有可用模型，请先发布模型后再启用 AI 研判",
            )
        if selected_model not in published_models:
            raise AppError(
                code="AI_MODEL_NOT_AVAILABLE",
                status_code=422,
                message="所选系统 Ollama 模型未发布或当前不可用",
                detail={"model": selected_model},
            )
        return selected_model

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
                message="未找到可用的外部 AI Provider",
            )
        if not provider.enabled:
            raise AppError(
                code="AI_PROVIDER_DISABLED",
                status_code=409,
                message="所选外部 AI Provider 已被禁用",
            )

        catalog_state = _probe_user_provider_model_catalog(provider)
        if not bool(catalog_state.get("available")):
            raise AppError(
                code="AI_PROVIDER_NOT_AVAILABLE",
                status_code=409,
                message="所选外部 AI Provider 当前不可用",
                detail={
                    "status_reason": catalog_state.get("status_reason"),
                    "connection_ok": catalog_state.get("connection_ok"),
                },
            )

        selected_model = normalized_model or provider.default_model
        if not selected_model:
            raise AppError(
                code="AI_MODEL_NOT_AVAILABLE",
                status_code=422,
                message="请填写要调用的模型名称",
            )

        live_model_names = catalog_state.get("live_model_names")
        if isinstance(live_model_names, list) and live_model_names:
            if selected_model not in live_model_names:
                raise AppError(
                    code="AI_MODEL_NOT_AVAILABLE",
                    status_code=422,
                    message="所选模型不在当前可用模型列表中",
                    detail={"model": selected_model},
                )
        elif not bool(catalog_state.get("allow_manual_model_input")):
            raise AppError(
                code="AI_MODEL_NOT_AVAILABLE",
                status_code=422,
                message="当前无法确认模型可用性，请稍后重试",
            )
        return selected_model

    raise AppError(
        code="INVALID_ARGUMENT",
        status_code=422,
        message="ai_source 值不合法",
        detail={"allowed_values": [AI_SOURCE_SYSTEM_OLLAMA, AI_SOURCE_USER_EXTERNAL]},
    )


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
            result = _run_assessment_for_finding(
                session,
                finding=finding,
                ai_job=job,
                provider_snapshot=provider_snapshot,
            )
            if result.ok:
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
            else:
                failed_count += 1
                _append_ai_log(
                    job_id=job.id,
                    stage=JobStage.AI.value,
                    message=(
                        f"研判失败: finding_id={finding.id}, code={result.assessment.error_code},"
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
        "request_messages_json": assessment.request_messages_json,
        "context_snapshot_json": assessment.context_snapshot_json,
        "response_text": assessment.response_text,
        "error_code": assessment.error_code,
        "error_message": assessment.error_message,
        "created_by": assessment.created_by,
        "created_at": assessment.created_at,
        "updated_at": assessment.updated_at,
    }


def build_finding_ai_review_summary(
    assessment: FindingAIAssessment | None,
) -> dict[str, object]:
    if assessment is None:
        return {
            "has_assessment": False,
            "assessment_id": None,
            "status": None,
            "verdict": None,
            "confidence": None,
            "updated_at": None,
        }
    summary = (
        dict(assessment.summary_json or {})
        if isinstance(assessment.summary_json, dict)
        else {}
    )
    verdict = _normalize_optional_text(summary.get("verdict"))
    confidence = _normalize_optional_text(summary.get("confidence"))
    return {
        "has_assessment": True,
        "assessment_id": assessment.id,
        "status": assessment.status,
        "verdict": verdict.upper() if verdict else None,
        "confidence": confidence.lower() if confidence else None,
        "updated_at": assessment.updated_at,
    }


def map_latest_finding_ai_assessments(
    db: Session, *, finding_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FindingAIAssessment]:
    normalized_ids = [item for item in finding_ids if isinstance(item, uuid.UUID)]
    if not normalized_ids:
        return {}
    rows = db.scalars(
        select(FindingAIAssessment)
        .where(FindingAIAssessment.finding_id.in_(normalized_ids))
        .order_by(
            FindingAIAssessment.finding_id.asc(),
            FindingAIAssessment.created_at.desc(),
        )
    ).all()
    latest_by_finding: dict[uuid.UUID, FindingAIAssessment] = {}
    for row in rows:
        if row.finding_id not in latest_by_finding:
            latest_by_finding[row.finding_id] = row
    return latest_by_finding


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
        seed_kind=None,
        seed_assessment_id=None,
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
        seed_kind=None,
        seed_assessment_id=None,
    )


def create_assessment_seed_chat_session(
    db: Session,
    *,
    finding: Finding,
    assessment: FindingAIAssessment,
    created_by: uuid.UUID,
) -> tuple[AIChatSession, bool]:
    if assessment.status != AIAssessmentStatus.SUCCEEDED.value:
        raise AppError(
            code="AI_ASSESSMENT_NOT_READY",
            status_code=409,
            message="当前最新 AI 研判尚未成功，暂时无法创建承接会话",
        )
    existing = db.scalar(
        select(AIChatSession).where(
            AIChatSession.created_by == created_by,
            AIChatSession.seed_assessment_id == assessment.id,
        )
    )
    if existing is not None:
        return existing, True

    provider_snapshot = _resolve_assessment_provider_snapshot(db, assessment=assessment)
    session = _create_chat_session_record(
        db,
        session_mode=AIChatSessionMode.FINDING_CONTEXT.value,
        finding=finding,
        created_by=created_by,
        provider_snapshot=provider_snapshot,
        title=_build_seed_session_title(finding=finding),
        seed_kind=AI_CHAT_SESSION_SEED_ASSESSMENT,
        seed_assessment_id=assessment.id,
    )

    request_messages = _resolve_assessment_request_messages(
        db,
        finding=finding,
        assessment=assessment,
        provider_snapshot=provider_snapshot,
    )
    create_chat_user_message(
        db,
        session=session,
        content=_render_seed_request_content(request_messages),
        meta_json={
            "message_kind": "assessment_seed_input",
            "assessment_id": str(assessment.id),
            "exclude_from_model_context": True,
        },
    )
    create_chat_assistant_message(
        db,
        session=session,
        content=_render_seed_response_content(assessment),
        raw_payload={"assessment_id": str(assessment.id)},
        meta_json={
            "message_kind": "assessment_seed_output",
            "assessment_id": str(assessment.id),
            "exclude_from_model_context": True,
        },
    )
    return session, False


def _create_chat_session_record(
    db: Session,
    *,
    session_mode: str,
    finding: Finding | None,
    created_by: uuid.UUID,
    provider_snapshot: dict[str, object],
    title: str | None,
    seed_kind: str | None,
    seed_assessment_id: uuid.UUID | None,
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
        seed_kind=_normalize_optional_text(seed_kind),
        seed_assessment_id=seed_assessment_id,
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
        "seed_kind": session.seed_kind,
        "seed_assessment_id": session.seed_assessment_id,
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
    meta_json: dict[str, object] | None = None,
) -> AIChatMessage:
    user_message = AIChatMessage(
        session_id=session.id,
        role=AIChatRole.USER.value,
        content=_normalize_required_text(content, field_name="content"),
        meta_json=dict(meta_json or {}),
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
    history = _chat_history_for_model(list_chat_messages(db, session_id=session.id))
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


def _chat_history_for_model(history: list[AIChatMessage]) -> list[AIChatMessage]:
    filtered: list[AIChatMessage] = []
    for item in history:
        meta = item.meta_json if isinstance(item.meta_json, dict) else {}
        if bool(meta.get("exclude_from_model_context")):
            continue
        filtered.append(item)
    return filtered


def create_chat_assistant_message(
    db: Session,
    *,
    session: AIChatSession,
    content: str,
    raw_payload: dict[str, object],
    meta_json: dict[str, object] | None = None,
) -> AIChatMessage:
    assistant_message = AIChatMessage(
        session_id=session.id,
        role=AIChatRole.ASSISTANT.value,
        content=content,
        meta_json={"raw_payload": raw_payload, **dict(meta_json or {})},
    )
    db.add(assistant_message)
    session.updated_at = utc_now()
    db.flush()
    return assistant_message


def _resolve_assessment_provider_snapshot(
    db: Session, *, assessment: FindingAIAssessment
) -> dict[str, object]:
    job = db.get(Job, assessment.job_id)
    payload = job.payload if job is not None and isinstance(job.payload, dict) else {}
    snapshot = payload.get("provider_snapshot") if isinstance(payload, dict) else None
    if isinstance(snapshot, dict) and snapshot:
        return dict(snapshot)
    raise AppError(
        code="AI_PROVIDER_SNAPSHOT_MISSING",
        status_code=409,
        message="当前 AI 研判缺少 Provider 快照，无法创建承接会话",
    )


def _resolve_assessment_request_messages(
    db: Session,
    *,
    finding: Finding,
    assessment: FindingAIAssessment,
    provider_snapshot: dict[str, object],
) -> list[dict[str, str]]:
    stored_messages = assessment.request_messages_json
    if isinstance(stored_messages, list) and stored_messages:
        normalized_messages: list[dict[str, str]] = []
        for item in stored_messages:
            if not isinstance(item, dict):
                continue
            role = _normalize_optional_text(item.get("role")) or "user"
            content = _normalize_optional_text(item.get("content"))
            if content is None:
                continue
            normalized_messages.append({"role": role, "content": content})
        if normalized_messages:
            return normalized_messages
    prompt_bundle = _build_assessment_messages(
        db,
        finding=finding,
        provider_snapshot=_prepare_assessment_provider_snapshot(
            _inflate_provider_snapshot(provider_snapshot)
        ),
    )
    return prompt_bundle.messages


def _render_seed_request_content(request_messages: list[dict[str, str]]) -> str:
    sections: list[str] = ["以下为本次 AI 研判实际发送内容："]
    for item in request_messages:
        role = str(item.get("role") or "user").strip().upper() or "USER"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        sections.append(f"[{role}]\n{content}")
    rendered = "\n\n".join(sections).strip()
    return rendered or "以下为本次 AI 研判实际发送内容：\n[USER]\n(空)"


def _render_seed_response_content(assessment: FindingAIAssessment) -> str:
    response_text = _normalize_optional_text(assessment.response_text)
    if response_text is not None:
        return response_text
    summary = (
        assessment.summary_json if isinstance(assessment.summary_json, dict) else {}
    )
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    return rendered if rendered.strip() else "模型未返回可展示的内容。"


def _build_seed_session_title(*, finding: Finding) -> str:
    return _truncate_text(
        f"{finding.vuln_type or finding.rule_key or '漏洞'} · AI 研判会话",
        255,
    )


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
    prompt_bundle: AssessmentPromptBundle | None = None
    try:
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
        assessment = _ensure_finding_ai_assessment_record(
            db,
            finding=finding,
            ai_job=ai_job,
            provider_snapshot=provider_snapshot,
        )
        assessment.status = AIAssessmentStatus.SUCCEEDED.value
        assessment.summary_json = {**summary, "prompt_meta": prompt_bundle.budget_meta}
        assessment.request_messages_json = [
            {"role": item.get("role") or "user", "content": item.get("content") or ""}
            for item in prompt_bundle.messages
        ]
        assessment.context_snapshot_json = prompt_bundle.context_payload
        assessment.response_text = result.content
        assessment.error_code = None
        assessment.error_message = None
        db.flush()
        return AssessmentRunResult(assessment=assessment, ok=True)
    except AppError as exc:
        assessment = _record_failed_assessment(
            db,
            finding=finding,
            ai_job=ai_job,
            provider_snapshot=provider_snapshot,
            error_code=exc.code,
            error_message=exc.message,
            prompt_bundle=prompt_bundle,
        )
        return AssessmentRunResult(assessment=assessment, ok=False)


def _record_failed_assessment(
    db: Session,
    *,
    finding: Finding,
    ai_job: Job,
    provider_snapshot: dict[str, object],
    error_code: str,
    error_message: str,
    prompt_bundle: AssessmentPromptBundle | None = None,
) -> FindingAIAssessment:
    assessment = _ensure_finding_ai_assessment_record(
        db,
        finding=finding,
        ai_job=ai_job,
        provider_snapshot=provider_snapshot,
    )
    assessment.status = AIAssessmentStatus.FAILED.value
    assessment.summary_json = (
        {"prompt_meta": prompt_bundle.budget_meta} if prompt_bundle is not None else {}
    )
    assessment.request_messages_json = (
        [
            {"role": item.get("role") or "user", "content": item.get("content") or ""}
            for item in prompt_bundle.messages
        ]
        if prompt_bundle is not None
        else []
    )
    assessment.context_snapshot_json = (
        prompt_bundle.context_payload if prompt_bundle is not None else {}
    )
    assessment.response_text = None
    assessment.error_code = error_code
    assessment.error_message = error_message
    db.flush()
    return assessment


def _ensure_finding_ai_assessment_record(
    db: Session,
    *,
    finding: Finding,
    ai_job: Job,
    provider_snapshot: dict[str, object],
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


def _build_system_model_catalog_item(
    system_ollama: dict[str, object],
) -> dict[str, object]:
    published_models = _normalize_model_list(system_ollama.get("published_models"))
    connection_ok = system_ollama.get("connection_ok")
    available = bool(system_ollama.get("available")) and bool(published_models)
    status_label = "可用"
    status_reason = None
    if connection_ok is False:
        status_label = "连接失败"
        status_reason = "系统 Ollama 当前无法连接"
    elif not published_models:
        status_label = "未发布模型"
        status_reason = "系统 Ollama 尚未发布可用模型"
    elif not bool(system_ollama.get("available")):
        status_label = "不可用"
        status_reason = "系统 Ollama 当前未启用或不满足使用条件"

    return {
        "provider_source": AI_SOURCE_SYSTEM_OLLAMA,
        "provider_id": None,
        "provider_key": SYSTEM_OLLAMA_PROVIDER_KEY,
        "provider_label": str(system_ollama.get("display_name") or "System Ollama"),
        "provider_type": str(
            system_ollama.get("provider_type") or AIProviderType.OLLAMA_LOCAL.value
        ),
        "enabled": True,
        "default_model": _normalize_optional_text(system_ollama.get("default_model")),
        "available": available,
        "connection_ok": connection_ok,
        "model_catalog_ok": bool(published_models),
        "allow_manual_model_input": False,
        "source_label": "本地",
        "status_label": status_label,
        "status_reason": status_reason,
        "models": [
            {
                "name": model,
                "label": model,
                "is_default": model
                == _normalize_optional_text(system_ollama.get("default_model")),
                "selectable": available,
                "details": {},
            }
            for model in published_models
        ],
    }


def _build_user_provider_model_catalog_item(
    provider: UserAIProvider,
) -> dict[str, object]:
    catalog_state = _probe_user_provider_model_catalog(provider)
    models = _build_selected_user_provider_models(
        live_models=catalog_state.get("live_models"),
        selected_model=provider.default_model,
        selectable=bool(catalog_state.get("available")),
    )

    return {
        "provider_source": AI_SOURCE_USER_EXTERNAL,
        "provider_id": provider.id,
        "provider_key": None,
        "provider_label": provider.display_name,
        "provider_type": provider.provider_type,
        "enabled": provider.enabled,
        "default_model": provider.default_model,
        "available": bool(catalog_state.get("available")),
        "connection_ok": catalog_state.get("connection_ok"),
        "model_catalog_ok": catalog_state.get("model_catalog_ok"),
        "allow_manual_model_input": bool(catalog_state.get("allow_manual_model_input")),
        "source_label": "外部",
        "status_label": catalog_state.get("status_label"),
        "status_reason": catalog_state.get("status_reason"),
        "models": models,
    }


def _probe_user_provider_model_catalog(provider: UserAIProvider) -> dict[str, object]:
    return _probe_openai_compatible_model_catalog(
        base_url=provider.base_url,
        api_key=decrypt_secret(provider.api_key_encrypted),
        timeout_seconds=int(provider.timeout_seconds),
    )


def _probe_user_ai_provider(
    *,
    vendor_name: str,
    provider_label: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    selected_model: str | None = None,
    verify_selected_model: bool = False,
) -> dict[str, object]:
    normalized_vendor_name = _normalize_required_text(
        vendor_name, field_name="vendor_name"
    )
    normalized_base_url = _normalize_url(base_url)
    normalized_api_key = _normalize_required_text(api_key, field_name="api_key")
    normalized_selected_model = _normalize_optional_text(selected_model)

    catalog_state = _probe_openai_compatible_model_catalog(
        base_url=normalized_base_url,
        api_key=normalized_api_key,
        timeout_seconds=timeout_seconds,
    )
    models = _build_selectable_provider_models(
        catalog_state.get("live_models"),
        selected_model=normalized_selected_model,
        selectable=bool(catalog_state.get("available")),
    )
    selected_model_verification: dict[str, object] | None = None
    if (
        verify_selected_model
        and normalized_selected_model is not None
        and bool(catalog_state.get("available"))
    ):
        selected_model_verification = _verify_openai_compatible_model(
            provider_label=provider_label,
            vendor_name=normalized_vendor_name,
            base_url=normalized_base_url,
            api_key=normalized_api_key,
            timeout_seconds=timeout_seconds,
            model_name=normalized_selected_model,
        )

    overall_ok = bool(catalog_state.get("available"))
    if selected_model_verification is not None:
        overall_ok = overall_ok and bool(selected_model_verification.get("ok"))

    return {
        "ok": overall_ok,
        "provider_type": AIProviderType.OPENAI_COMPATIBLE.value,
        "provider_label": provider_label,
        "vendor_name": normalized_vendor_name,
        "base_url": normalized_base_url,
        "connection_ok": bool(catalog_state.get("connection_ok")),
        "model_catalog_ok": bool(catalog_state.get("model_catalog_ok")),
        "allow_manual_model_input": bool(catalog_state.get("allow_manual_model_input")),
        "status_label": catalog_state.get("status_label"),
        "status_reason": catalog_state.get("status_reason"),
        "model_count": len(catalog_state.get("live_model_names") or []),
        "models": models,
        "selected_model_verification": selected_model_verification,
    }


def _build_selectable_provider_models(
    live_models: object,
    *,
    selected_model: str | None,
    selectable: bool,
) -> list[dict[str, object]]:
    models: list[dict[str, object]] = []
    if not isinstance(live_models, list):
        return models
    for item in live_models:
        if not isinstance(item, dict):
            continue
        model_name = _normalize_optional_text(item.get("id") or item.get("name"))
        if model_name is None:
            continue
        models.append(
            {
                "name": model_name,
                "label": model_name,
                "is_default": model_name == selected_model,
                "selectable": selectable,
                "details": {
                    key: value
                    for key, value in item.items()
                    if key not in {"id", "name"}
                },
            }
        )
    return models


def _build_selected_user_provider_models(
    *,
    live_models: object,
    selected_model: str | None,
    selectable: bool,
) -> list[dict[str, object]]:
    normalized_selected_model = _normalize_optional_text(selected_model)
    if normalized_selected_model is None:
        return []

    matched_details: dict[str, object] = {}
    if isinstance(live_models, list):
        for item in live_models:
            if not isinstance(item, dict):
                continue
            model_name = _normalize_optional_text(item.get("id") or item.get("name"))
            if model_name != normalized_selected_model:
                continue
            matched_details = {
                key: value for key, value in item.items() if key not in {"id", "name"}
            }
            break

    return [
        {
            "name": normalized_selected_model,
            "label": normalized_selected_model,
            "is_default": True,
            "selectable": selectable,
            "details": matched_details,
        }
    ]


def _probe_openai_compatible_model_catalog(
    *, base_url: str, api_key: str, timeout_seconds: int
) -> dict[str, object]:
    try:
        live_models = list_openai_compatible_models(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=int(timeout_seconds),
        )
        live_model_names = [
            model_name
            for item in live_models
            if isinstance(item, dict)
            for model_name in [
                _normalize_optional_text(item.get("id") or item.get("name"))
            ]
            if model_name is not None
        ]
        allow_manual_model_input = not bool(live_model_names)
        return {
            "available": True,
            "connection_ok": True,
            "model_catalog_ok": True,
            "allow_manual_model_input": allow_manual_model_input,
            "status_label": "可用" if live_model_names else "可用，需手填模型",
            "status_reason": (
                None if live_model_names else "模型目录为空，请手动填写调用模型名称。"
            ),
            "live_models": live_models,
            "live_model_names": live_model_names,
        }
    except AppError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        status_code = _to_int(detail.get("status_code"))
        if exc.code == "AI_PROVIDER_INVALID_RESPONSE" or (
            exc.code == "AI_PROVIDER_HTTP_ERROR" and status_code in {404, 405}
        ):
            return {
                "available": True,
                "connection_ok": True,
                "model_catalog_ok": False,
                "allow_manual_model_input": True,
                "status_label": "目录不可用，需手填模型",
                "status_reason": "模型目录接口不可用，请手动填写调用模型名称。",
                "live_models": [],
                "live_model_names": [],
            }
        if exc.code == "AI_PROVIDER_HTTP_ERROR" and status_code in {401, 403}:
            return {
                "available": False,
                "connection_ok": False,
                "model_catalog_ok": False,
                "allow_manual_model_input": False,
                "status_label": "认证失败",
                "status_reason": "外部 Provider 密钥无效或无权访问模型目录。",
                "live_models": [],
                "live_model_names": [],
            }
        return {
            "available": False,
            "connection_ok": False,
            "model_catalog_ok": False,
            "allow_manual_model_input": False,
            "status_label": "连接失败",
            "status_reason": exc.message,
            "live_models": [],
            "live_model_names": [],
        }


def _verify_openai_compatible_model(
    *,
    provider_label: str,
    vendor_name: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    model_name: str,
) -> dict[str, object]:
    try:
        result = run_provider_chat(
            provider_snapshot={
                "provider_type": AIProviderType.OPENAI_COMPATIBLE.value,
                "display_name": provider_label,
                "vendor_name": vendor_name,
                "base_url": base_url,
                "model": model_name,
                "api_key": api_key,
                "timeout_seconds": int(timeout_seconds),
                "temperature": 0.0,
                "max_output_tokens": MODEL_VERIFICATION_MAX_OUTPUT_TOKENS,
            },
            messages=[{"role": "user", "content": MODEL_VERIFICATION_PROMPT}],
        )
        return {
            "model": model_name,
            "ok": True,
            "message": "模型验证成功，可用于当前聊天调用链路。",
            "response_preview": result.content[:120],
        }
    except AppError as exc:
        return {
            "model": model_name,
            "ok": False,
            "message": _describe_model_verification_error(exc),
            "error_code": exc.code,
            "response_preview": None,
        }


def _describe_model_verification_error(exc: AppError) -> str:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    status_code = _to_int(detail.get("status_code"))
    if exc.code == "AI_PROVIDER_HTTP_ERROR" and status_code == 429:
        return "模型验证失败：服务商当前限流或配额不足，请稍后重试。"
    if exc.code == "AI_PROVIDER_HTTP_ERROR" and status_code in {401, 403}:
        return "模型验证失败：API Key 无效，或当前密钥无权访问该模型。"
    if exc.code == "AI_PROVIDER_HTTP_ERROR" and status_code == 404:
        return "模型验证失败：当前模型不可用，或不支持该兼容调用方式。"
    if exc.code == "AI_PROVIDER_HTTP_ERROR" and status_code == 400:
        return (
            "模型验证失败：服务商拒绝了该模型请求，请确认模型名称与兼容接口是否匹配。"
        )
    if exc.code == "AI_CHAT_TIMEOUT":
        return "模型验证超时，请稍后重试。"
    if exc.code == "AI_PROVIDER_UNAVAILABLE":
        return "模型验证失败：AI Provider 当前不可用，请检查网络或服务状态。"
    return exc.message


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
    _prepare_assessment_prompt_context(prompt_context)
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


def _prepare_assessment_prompt_context(context_payload: dict[str, object]) -> None:
    extraction = (
        context_payload.get("extraction")
        if isinstance(context_payload.get("extraction"), dict)
        else None
    )
    if extraction is not None:
        extraction.pop("expanded_code_context", None)


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
    stored_extraction = (
        evidence.get("assessment_extraction")
        if isinstance(evidence.get("assessment_extraction"), dict)
        else {}
    )
    extraction = build_assessment_extraction(
        rule_key=finding.rule_key,
        vuln_type=(
            finding.vuln_type
            or (rule_meta.vuln_type if rule_meta is not None else None)
        ),
        source=source,
        sink=sink,
        trace_summary=trace_summary,
        code_context=code_context,
        evidence=evidence,
        data_flow_chain=(
            path_payload.get("data_flow_chain")
            if isinstance(path_payload.get("data_flow_chain"), list)
            else []
        ),
        source_highlights=(
            stored_extraction.get("source_highlights")
            if isinstance(stored_extraction.get("source_highlights"), list)
            else []
        ),
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
        "extraction": extraction,
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
    profile = resolve_assessment_profile(vuln_type=vuln_type, rule_key=rule_key)
    if profile in ASSESSMENT_PROFILE_HINTS:
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
    shrink_rounds = 0
    while input_tokens > int(budget_meta["max_input_tokens"]):
        if shrink_rounds >= 256:
            break
        changed = _shrink_assessment_context_payload(context_payload)
        if not changed:
            break
        next_prompt = _render_assessment_prompt_text(context_payload)
        if next_prompt == prompt:
            break
        prompt = next_prompt
        input_tokens = _estimate_text_tokens(prompt)
        shrink_rounds += 1
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
    extraction = (
        context_payload.get("extraction")
        if isinstance(context_payload.get("extraction"), dict)
        else None
    )
    if extraction is not None:
        expanded = (
            extraction.get("expanded_code_context")
            if isinstance(extraction.get("expanded_code_context"), dict)
            else None
        )
        if expanded is not None:
            for key in ("sink", "source", "focus"):
                value = _normalize_optional_text(expanded.get(key))
                if value and len(value) > 240:
                    expanded[key] = _truncate_text(value, max(240, len(value) // 2))
                    return True
                if value:
                    expanded.pop(key, None)
                    return True
            path_steps = expanded.get("path_steps")
            if isinstance(path_steps, list) and path_steps:
                expanded["path_steps"] = path_steps[:-1]
                if not expanded["path_steps"]:
                    expanded.pop("path_steps", None)
                return True
            if not expanded:
                extraction.pop("expanded_code_context", None)
                return True
        source_highlights = extraction.get("source_highlights")
        if isinstance(source_highlights, list):
            for item in source_highlights:
                if not isinstance(item, dict):
                    continue
                snippet = _normalize_optional_text(item.get("snippet"))
                if snippet and len(snippet) > 260:
                    item["snippet"] = _truncate_text(
                        snippet, max(260, len(snippet) // 2)
                    )
                    return True
            if len(source_highlights) > 2:
                extraction["source_highlights"] = source_highlights[:-1]
                return True
        filter_points = extraction.get("filter_points")
        if isinstance(filter_points, list) and len(filter_points) > 1:
            extraction["filter_points"] = filter_points[:-1]
            return True
        missing_evidence = extraction.get("missing_evidence")
        if isinstance(missing_evidence, list) and len(missing_evidence) > 1:
            extraction["missing_evidence"] = missing_evidence[:-1]
            return True
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
            if isinstance(chain, list) and chain:
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


def _resolve_user_provider_display_name(
    *, display_name: object | None, default_model: object
) -> str:
    normalized_display_name = _normalize_optional_text(display_name)
    if normalized_display_name is not None:
        return normalized_display_name
    return _normalize_required_text(default_model, field_name="default_model")


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


def _canonicalize_ollama_model_name(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="model_name")
    if "@" in normalized:
        return normalized
    tail = normalized.rsplit("/", 1)[-1]
    if ":" in tail:
        return normalized
    return f"{normalized}:latest"


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
