from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
import shutil
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import (
    FindingSeverity,
    RuleStat,
    SelfTestJob,
    SelfTestJobStage,
    SelfTestJobStatus,
    SystemRole,
    utc_now,
)
from app.schemas.rule import (
    RuleCreateRequest,
    RuleDraftUpdateRequest,
    RuleListPayload,
    RulePayload,
    RuleRollbackRequest,
    RuleSetBindRulesRequest,
    RuleSetCreateRequest,
    RuleSetDetailPayload,
    RuleSetItemPayload,
    RuleSetListPayload,
    RuleSetPayload,
    RuleSelfTestCreateRequest,
    RuleSelfTestPayload,
    RuleSelfTestTriggerPayload,
    RuleStatListPayload,
    RuleStatPayload,
    RuleSetUpdateRequest,
    RuleToggleRequest,
    RuleVersionListPayload,
    RuleVersionPayload,
)
from app.schemas.task_log import TaskLogEntryPayload, TaskLogPayload
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.rule_file_service import (
    RuleFileRecord,
    RuleFileVersionRecord,
    create_rule as create_file_rule,
    get_rule as get_file_rule,
    list_rule_versions as list_file_rule_versions,
    list_rules as list_file_rules,
    publish_rule as publish_file_rule,
    rollback_rule as rollback_file_rule,
    toggle_rule as toggle_file_rule,
    update_rule_draft as update_file_rule_draft,
)
from app.services.rule_set_file_service import (
    RuleSetFileItemRecord,
    RuleSetFileRecord,
    bind_rule_set_rules as bind_rule_set_file_rules,
    build_rule_set_items,
    create_rule_set as create_file_rule_set,
    get_rule_set as get_file_rule_set,
    list_rule_sets as list_file_rule_sets,
    normalize_rule_set_key,
    update_rule_set as update_file_rule_set,
)
from app.services.selftest_service import (
    create_selftest_job,
    dispatch_selftest_job,
    mark_selftest_dispatch_failed,
    selftest_failure_hint_for_code,
)
from app.services.task_log_service import (
    build_task_logs_zip_bytes,
    build_task_stage_log_bytes,
    read_task_logs,
    sync_task_log_index,
)


router = APIRouter(tags=["rules"])

RULE_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _can_view_rule_drafts(principal: AuthPrincipal) -> bool:
    return principal.user.role == SystemRole.ADMIN.value


def _normalize_rule_key(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().endswith(".cypher"):
        normalized = normalized[:-7]
    if not normalized:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="rule_key 不能为空"
        )
    if len(normalized) > 128 or not RULE_KEY_RE.fullmatch(normalized):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_key 仅支持字母数字以及 ._-，且长度不超过 128",
        )
    return normalized


def _normalize_severity(value: str) -> str:
    normalized = value.strip().upper()
    allowed = {item.value for item in FindingSeverity}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="default_severity 值不合法",
            detail={"allowed_values": sorted(allowed)},
        )
    return normalized


def _rule_payload(rule: RuleFileRecord) -> RulePayload:
    return RulePayload(
        rule_key=rule.rule_key,
        name=rule.name,
        vuln_type=rule.vuln_type,
        default_severity=rule.default_severity,
        language_scope=rule.language_scope,
        description=rule.description,
        enabled=rule.enabled,
        active_version=rule.active_version,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _rule_version_payload(version: RuleFileVersionRecord) -> RuleVersionPayload:
    return RuleVersionPayload(
        id=version.id,
        rule_key=version.rule_key,
        version=version.version,
        status=version.status,
        content=version.content,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _rule_set_payload(
    rule_set: RuleSetFileRecord, *, rule_count: int
) -> RuleSetPayload:
    return RuleSetPayload(
        id=rule_set.id,
        key=rule_set.key,
        name=rule_set.name,
        description=rule_set.description,
        enabled=rule_set.enabled,
        rule_count=rule_count,
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
    )


def _rule_set_item_payload(item: RuleSetFileItemRecord) -> RuleSetItemPayload:
    return RuleSetItemPayload(
        id=item.id,
        rule_set_id=item.rule_set_id,
        rule_key=item.rule_key,
        created_at=item.created_at,
    )


def _rule_stat_payload(item: RuleStat) -> RuleStatPayload:
    return RuleStatPayload(
        rule_key=item.rule_key,
        rule_version=item.rule_version,
        metric_date=item.metric_date,
        hits=item.hits,
        avg_duration_ms=item.avg_duration_ms,
        timeout_count=item.timeout_count,
        fp_count=item.fp_count,
    )


def _selftest_job_payload(job: SelfTestJob) -> RuleSelfTestPayload:
    return RuleSelfTestPayload(
        id=job.id,
        rule_key=job.rule_key,
        rule_version=job.rule_version,
        payload=job.payload,
        status=job.status,
        stage=job.stage,
        failure_code=job.failure_code,
        failure_hint=job.failure_hint
        or selftest_failure_hint_for_code(job.failure_code),
        result_summary=job.result_summary,
        created_by=job.created_by,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _parse_optional_draft_payload(value: str | None) -> dict | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="draft_payload 不是合法 JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="draft_payload 必须是对象",
        )
    return parsed


def _upload_archive_suffix(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".zip"):
        return ".zip"
    if lower.endswith(".tar.gz"):
        return ".tar.gz"
    if lower.endswith(".tgz"):
        return ".tgz"
    raise AppError(
        code="ARCHIVE_INVALID", status_code=422, message="仅支持 zip/tar.gz 文件"
    )


def _save_selftest_upload(*, job_id: uuid.UUID, upload: UploadFile) -> tuple[Path, int]:
    settings = get_settings()
    filename = upload.filename or "selftest.zip"
    suffix = _upload_archive_suffix(filename)
    workspace = Path(settings.import_workspace_root) / str(job_id)
    workspace.mkdir(parents=True, exist_ok=True)
    archive_path = workspace / f"selftest{suffix}"

    total = 0
    with archive_path.open("wb") as destination:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.import_upload_max_bytes:
                raise AppError(
                    code="UPLOAD_TOO_LARGE",
                    status_code=413,
                    message="上传文件超出大小限制",
                )
            destination.write(chunk)

    return archive_path, total


def _mark_selftest_failed_for_input(
    db: Session, *, job_id: uuid.UUID, failure_code: str
) -> None:
    job = db.get(SelfTestJob, job_id)
    if job is None:
        return
    now = utc_now()
    job.status = SelfTestJobStatus.FAILED.value
    job.stage = SelfTestJobStage.PREPARE.value
    job.failure_code = failure_code
    job.failure_hint = selftest_failure_hint_for_code(failure_code)
    job.finished_at = now
    if job.started_at is None:
        job.started_at = now
    db.commit()


@router.get("/api/v1/rules")
def list_rules(
    request: Request,
    enabled: bool | None = None,
    vuln_type: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    _db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:read")),
):
    include_drafts = _can_view_rule_drafts(principal)
    rows, total = list_file_rules(
        enabled=enabled,
        vuln_type=vuln_type,
        search=search,
        page=page,
        page_size=page_size,
        published_only=not include_drafts,
        include_draft_metadata=include_drafts,
    )
    payload = RuleListPayload(items=[_rule_payload(item) for item in rows], total=total)
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/rules/{rule_key}")
def get_rule(
    request: Request,
    rule_key: str,
    _db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:read")),
):
    include_drafts = _can_view_rule_drafts(principal)
    rule = get_file_rule(
        _normalize_rule_key(rule_key),
        published_only=not include_drafts,
        include_draft_metadata=include_drafts,
    )
    return success_response(request, data=_rule_payload(rule).model_dump())


@router.get("/api/v1/rules/{rule_key}/versions")
def list_rule_versions(
    request: Request,
    rule_key: str,
    _db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:read")),
):
    normalized_rule_key = _normalize_rule_key(rule_key)
    rows = list_file_rule_versions(
        normalized_rule_key,
        published_only=not _can_view_rule_drafts(principal),
    )
    payload = RuleVersionListPayload(
        items=[_rule_version_payload(item) for item in rows],
        total=len(rows),
    )
    return success_response(request, data=payload.model_dump())


@router.post("/api/v1/rules")
def create_rule(
    request: Request,
    payload: RuleCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:write")),
):
    rule_key = _normalize_rule_key(payload.rule_key)
    rule, _draft_version = create_file_rule(
        rule_key=rule_key,
        name=payload.name,
        vuln_type=payload.vuln_type,
        default_severity=_normalize_severity(payload.default_severity),
        language_scope=payload.language_scope,
        description=payload.description,
        content=payload.content,
        created_by=principal.user.id,
    )

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule.create",
        resource_type="RULE",
        resource_id=rule_key,
        detail_json={
            "vuln_type": rule.vuln_type,
            "language_scope": rule.language_scope,
        },
    )
    db.commit()
    return success_response(
        request, data=_rule_payload(rule).model_dump(), status_code=201
    )


@router.patch("/api/v1/rules/{rule_key}/draft")
def update_rule_draft(
    request: Request,
    rule_key: str,
    payload: RuleDraftUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:write")),
):
    normalized_rule_key = _normalize_rule_key(rule_key)
    normalized_severity = (
        _normalize_severity(payload.default_severity)
        if payload.default_severity is not None
        else None
    )

    rule, draft = update_file_rule_draft(
        rule_key=normalized_rule_key,
        updates={
            "name": payload.name,
            "vuln_type": payload.vuln_type,
            "default_severity": normalized_severity,
            "language_scope": payload.language_scope,
            "description": payload.description,
            "content": payload.content,
        },
        operator_id=principal.user.id,
    )

    changes: dict[str, object] = {"draft_version": draft.version}
    if payload.name is not None:
        changes["name"] = payload.name.strip()
    if payload.vuln_type is not None:
        changes["vuln_type"] = payload.vuln_type.strip()
    if normalized_severity is not None:
        changes["default_severity"] = normalized_severity
    if payload.language_scope is not None:
        changes["language_scope"] = payload.language_scope.strip()
    if payload.description is not None:
        changes["description"] = payload.description
    if payload.content is not None:
        changes["content_updated"] = True

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule.draft.update",
        resource_type="RULE",
        resource_id=normalized_rule_key,
        detail_json=changes,
    )
    db.commit()
    return success_response(
        request,
        data={
            "rule": _rule_payload(rule).model_dump(),
            "draft_version": _rule_version_payload(draft).model_dump(),
        },
    )


@router.post("/api/v1/rules/{rule_key}/publish")
def publish_rule(
    request: Request,
    rule_key: str,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:publish")),
):
    normalized_rule_key = _normalize_rule_key(rule_key)
    rule, draft = publish_file_rule(
        rule_key=normalized_rule_key,
        operator_id=principal.user.id,
    )

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule.publish",
        resource_type="RULE",
        resource_id=normalized_rule_key,
        detail_json={"published_version": draft.version},
    )
    db.commit()
    return success_response(
        request,
        data={
            "rule": _rule_payload(rule).model_dump(),
            "published_version": _rule_version_payload(draft).model_dump(),
        },
    )


@router.post("/api/v1/rules/{rule_key}/rollback")
def rollback_rule(
    request: Request,
    rule_key: str,
    payload: RuleRollbackRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:publish")),
):
    normalized_rule_key = _normalize_rule_key(rule_key)
    rule = rollback_file_rule(rule_key=normalized_rule_key, version=payload.version)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule.rollback",
        resource_type="RULE",
        resource_id=normalized_rule_key,
        detail_json={"active_version": payload.version},
    )
    db.commit()
    return success_response(request, data=_rule_payload(rule).model_dump())


@router.post("/api/v1/rules/{rule_key}/toggle")
def toggle_rule(
    request: Request,
    rule_key: str,
    payload: RuleToggleRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:toggle")),
):
    normalized_rule_key = _normalize_rule_key(rule_key)
    before_rule = get_file_rule(rule_key=normalized_rule_key)
    rule = toggle_file_rule(rule_key=normalized_rule_key, enabled=payload.enabled)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule.toggle",
        resource_type="RULE",
        resource_id=normalized_rule_key,
        detail_json={
            "context": {"rule_key": normalized_rule_key},
            "change": {
                "before_enabled": bool(before_rule.enabled),
                "after_enabled": bool(payload.enabled),
            },
            "outcome": {"status": "SUCCEEDED"},
        },
    )
    db.commit()
    return success_response(request, data=_rule_payload(rule).model_dump())


@router.get("/api/v1/rule-stats")
def list_rule_stats(
    request: Request,
    rule_key: str | None = None,
    metric_date_from: str | None = None,
    metric_date_to: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("rule:read")),
):
    conditions = []
    if rule_key is not None and rule_key.strip():
        conditions.append(RuleStat.rule_key == _normalize_rule_key(rule_key))
    if metric_date_from is not None and metric_date_from.strip():
        try:
            parsed_from = date.fromisoformat(metric_date_from.strip())
        except ValueError as exc:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="metric_date_from 格式必须为 YYYY-MM-DD",
            ) from exc
        conditions.append(RuleStat.metric_date >= parsed_from)
    if metric_date_to is not None and metric_date_to.strip():
        try:
            parsed_to = date.fromisoformat(metric_date_to.strip())
        except ValueError as exc:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="metric_date_to 格式必须为 YYYY-MM-DD",
            ) from exc
        conditions.append(RuleStat.metric_date <= parsed_to)

    total_stmt = select(func.count()).select_from(RuleStat)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = db.scalar(total_stmt) or 0

    rows_stmt = select(RuleStat)
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = db.scalars(
        rows_stmt.order_by(
            RuleStat.metric_date.desc(),
            RuleStat.rule_key.asc(),
            RuleStat.rule_version.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    payload = RuleStatListPayload(
        items=[_rule_stat_payload(item) for item in rows], total=total
    )
    return success_response(request, data=payload.model_dump())


@router.post("/api/v1/rules/selftest")
def create_rule_selftest(
    request: Request,
    payload: RuleSelfTestCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:selftest")),
):
    request_id = get_request_id(request)
    has_rule_key = bool((payload.rule_key or "").strip())
    has_draft_payload = payload.draft_payload is not None
    if has_rule_key == has_draft_payload:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_key 与 draft_payload 必须二选一",
        )
    if payload.rule_version is not None and not has_rule_key:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="仅当指定 rule_key 时可传 rule_version",
        )
    if payload.version_id is None:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="请提供 version_id 或使用 /rules/selftest/upload 接口",
        )

    normalized_rule_key = (
        _normalize_rule_key(payload.rule_key or "") if has_rule_key else None
    )
    job = create_selftest_job(
        db,
        rule_key=normalized_rule_key,
        rule_version=payload.rule_version,
        payload={
            "request_id": request_id,
            "version_id": str(payload.version_id),
            "draft_payload": payload.draft_payload,
        },
        created_by=principal.user.id,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="rule.selftest.triggered",
        resource_type="SELFTEST_JOB",
        resource_id=str(job.id),
        detail_json={
            "rule_key": normalized_rule_key,
            "rule_version": payload.rule_version,
            "version_id": str(payload.version_id),
            "target_type": "VERSION",
        },
    )
    db.commit()

    try:
        dispatch_selftest_job(db, job=job)
    except AppError as exc:
        if exc.code == "SELFTEST_DISPATCH_FAILED":
            mark_selftest_dispatch_failed(
                db,
                job_id=job.id,
                request_id=request_id,
                operator_user_id=principal.user.id,
            )
        raise

    data = RuleSelfTestTriggerPayload(selftest_job_id=job.id)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.post("/api/v1/rules/selftest/upload")
def create_rule_selftest_upload(
    request: Request,
    file: UploadFile = File(...),
    rule_key: str | None = Form(default=None),
    rule_version: int | None = Form(default=None),
    draft_payload: str | None = Form(default=None),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:selftest")),
):
    request_id = get_request_id(request)
    normalized_rule_key = (rule_key or "").strip() or None
    parsed_draft_payload = _parse_optional_draft_payload(draft_payload)

    has_rule_key = normalized_rule_key is not None
    has_draft_payload = parsed_draft_payload is not None
    if has_rule_key == has_draft_payload:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="rule_key 与 draft_payload 必须二选一",
        )
    if rule_version is not None and not has_rule_key:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="仅当指定 rule_key 时可传 rule_version",
        )

    validated_rule_key = (
        _normalize_rule_key(normalized_rule_key) if normalized_rule_key else None
    )
    original_filename = file.filename or "selftest.zip"
    job = create_selftest_job(
        db,
        rule_key=validated_rule_key,
        rule_version=rule_version,
        payload={
            "request_id": request_id,
            "original_filename": original_filename,
            "draft_payload": parsed_draft_payload,
        },
        created_by=principal.user.id,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=principal.user.id,
        action="rule.selftest.upload.triggered",
        resource_type="SELFTEST_JOB",
        resource_id=str(job.id),
        detail_json={
            "rule_key": validated_rule_key,
            "rule_version": rule_version,
            "filename": original_filename,
            "target_type": "UPLOAD",
        },
    )
    db.commit()

    try:
        archive_path, size_bytes = _save_selftest_upload(job_id=job.id, upload=file)
    except AppError as exc:
        shutil.rmtree(
            Path(get_settings().import_workspace_root) / str(job.id), ignore_errors=True
        )
        _mark_selftest_failed_for_input(db, job_id=job.id, failure_code=exc.code)
        raise

    refreshed = db.get(SelfTestJob, job.id)
    if refreshed is not None:
        refreshed.payload = {
            **(refreshed.payload or {}),
            "archive_path": str(archive_path),
            "size_bytes": size_bytes,
        }
        db.commit()

    try:
        dispatch_selftest_job(db, job=job)
    except AppError as exc:
        if exc.code == "SELFTEST_DISPATCH_FAILED":
            mark_selftest_dispatch_failed(
                db,
                job_id=job.id,
                request_id=request_id,
                operator_user_id=principal.user.id,
            )
        raise

    data = RuleSelfTestTriggerPayload(selftest_job_id=job.id)
    return success_response(request, data=data.model_dump(), status_code=202)


@router.get("/api/v1/rules/selftest/{selftest_job_id}")
def get_rule_selftest_job(
    request: Request,
    selftest_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("rule:selftest")),
):
    job = db.get(SelfTestJob, selftest_job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="规则自测任务不存在")
    return success_response(request, data=_selftest_job_payload(job).model_dump())


@router.get("/api/v1/rules/selftest/{selftest_job_id}/logs")
def get_rule_selftest_logs(
    request: Request,
    selftest_job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    tail: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("rule:selftest")),
):
    job = db.get(SelfTestJob, selftest_job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="规则自测任务不存在")

    sync_task_log_index(task_type="SELFTEST", task_id=job.id, project_id=None, db=db)

    items = read_task_logs(task_type="SELFTEST", task_id=job.id, stage=stage, tail=tail)
    payload = TaskLogPayload(
        task_type="SELFTEST",
        task_id=job.id,
        items=[TaskLogEntryPayload(**item) for item in items],
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/rules/selftest/{selftest_job_id}/logs/download")
def download_rule_selftest_logs(
    request: Request,
    selftest_job_id: uuid.UUID,
    stage: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("rule:selftest")),
):
    job = db.get(SelfTestJob, selftest_job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="规则自测任务不存在")

    sync_task_log_index(task_type="SELFTEST", task_id=job.id, project_id=None, db=db)

    if stage is not None and stage.strip():
        content = build_task_stage_log_bytes(
            task_type="SELFTEST",
            task_id=job.id,
            stage=stage.strip(),
        )
        filename = f"{job.id}_{stage.strip()}.log"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    archive_bytes = build_task_logs_zip_bytes(task_type="SELFTEST", task_id=job.id)
    filename = f"selftest_job_{job.id}_logs.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(archive_bytes), media_type="application/zip", headers=headers
    )


@router.get("/api/v1/rule-sets")
def list_rule_sets(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("rule:read")),
):
    rows, total = list_file_rule_sets(page=page, page_size=page_size)

    payload = RuleSetListPayload(
        items=[
            _rule_set_payload(item, rule_count=len(item.rule_keys)) for item in rows
        ],
        total=total,
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/rule-sets/{rule_set_id}")
def get_rule_set(
    request: Request,
    rule_set_id: uuid.UUID,
    _db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("rule:read")),
):
    rule_set = get_file_rule_set(rule_set_id=rule_set_id)
    items = build_rule_set_items(rule_set)
    payload = RuleSetDetailPayload(
        id=rule_set.id,
        key=rule_set.key,
        name=rule_set.name,
        description=rule_set.description,
        enabled=rule_set.enabled,
        items=[_rule_set_item_payload(item) for item in items],
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
    )
    return success_response(request, data=payload.model_dump())


@router.post("/api/v1/rule-sets")
def create_rule_set(
    request: Request,
    payload: RuleSetCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:write")),
):
    rule_set = create_file_rule_set(
        key=normalize_rule_set_key(payload.key),
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
    )

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule_set.create",
        resource_type="RULE_SET",
        resource_id=str(rule_set.id),
        detail_json={"key": rule_set.key, "name": rule_set.name},
    )
    db.commit()
    return success_response(
        request,
        data=_rule_set_payload(rule_set, rule_count=0).model_dump(),
        status_code=201,
    )


@router.patch("/api/v1/rule-sets/{rule_set_id}")
def update_rule_set(
    request: Request,
    rule_set_id: uuid.UUID,
    payload: RuleSetUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:write")),
):
    before = get_file_rule_set(rule_set_id=rule_set_id)
    updates: dict[str, object] = {}
    if "name" in payload.model_fields_set:
        updates["name"] = payload.name
    if "description" in payload.model_fields_set:
        updates["description"] = payload.description
    if "enabled" in payload.model_fields_set:
        updates["enabled"] = payload.enabled

    rule_set = update_file_rule_set(rule_set_id=rule_set_id, **updates)

    changes: dict[str, object] = {}
    if before.name != rule_set.name:
        changes["name"] = {"before": before.name, "after": rule_set.name}
    if before.description != rule_set.description:
        changes["description"] = {
            "before": before.description,
            "after": rule_set.description,
        }
    if before.enabled != rule_set.enabled:
        changes["enabled"] = {"before": before.enabled, "after": rule_set.enabled}

    if changes:
        append_audit_log(
            db,
            request_id=get_request_id(request),
            operator_user_id=principal.user.id,
            action="rule_set.update",
            resource_type="RULE_SET",
            resource_id=str(rule_set.id),
            detail_json=changes,
        )
    db.commit()

    return success_response(
        request,
        data=_rule_set_payload(
            rule_set, rule_count=len(rule_set.rule_keys)
        ).model_dump(),
    )


@router.post("/api/v1/rule-sets/{rule_set_id}/rules")
def bind_rule_set_rules(
    request: Request,
    rule_set_id: uuid.UUID,
    payload: RuleSetBindRulesRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("rule:write")),
):
    rule_set = bind_rule_set_file_rules(
        rule_set_id=rule_set_id,
        rule_keys=payload.rule_keys,
    )

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="rule_set.bind_rules",
        resource_type="RULE_SET",
        resource_id=str(rule_set.id),
        detail_json={"item_count": len(rule_set.rule_keys)},
    )
    db.commit()

    items = build_rule_set_items(rule_set)
    detail = RuleSetDetailPayload(
        id=rule_set.id,
        key=rule_set.key,
        name=rule_set.name,
        description=rule_set.description,
        enabled=rule_set.enabled,
        items=[_rule_set_item_payload(item) for item in items],
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
    )
    return success_response(request, data=detail.model_dump())
