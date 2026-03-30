from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    SystemAIProvider,
    SystemOllamaPullJob,
    SystemOllamaPullJobStage,
    SystemOllamaPullJobStatus,
    TaskLogType,
    utc_now,
)
from app.services.ai_client_service import list_ollama_models, stream_ollama_model_pull
from app.services.audit_service import append_audit_log
from app.services.task_log_service import append_task_log


ACTIVE_PULL_STATUSES = {
    SystemOllamaPullJobStatus.PENDING.value,
    SystemOllamaPullJobStatus.RUNNING.value,
}
TERMINAL_PULL_STATUSES = {
    SystemOllamaPullJobStatus.SUCCEEDED.value,
    SystemOllamaPullJobStatus.FAILED.value,
    SystemOllamaPullJobStatus.CANCELED.value,
    SystemOllamaPullJobStatus.TIMEOUT.value,
}
PULL_TIMEOUT_CODES = {"OLLAMA_PULL_TIMEOUT"}

PULL_FAILURE_HINTS: dict[str, str] = {
    "AI_PROVIDER_DISABLED": "系统 Ollama 已被禁用，请先启用后再重试。",
    "AI_PROVIDER_HTTP_ERROR": "Ollama 请求失败，请检查服务状态或模型名称。",
    "AI_PROVIDER_UNAVAILABLE": "Ollama 当前不可用，请检查网络或服务进程。",
    "AI_PROVIDER_INVALID_RESPONSE": "Ollama 返回了无法识别的响应，请稍后重试。",
    "OLLAMA_PULL_ALREADY_RUNNING": "当前已有其他模型拉取任务在执行，请等待完成后再试。",
    "OLLAMA_PULL_DISPATCH_FAILED": "模型拉取任务派发失败，请检查 Worker 或调度器状态。",
    "OLLAMA_PULL_INTERNAL_ERROR": "模型拉取执行异常，请稍后重试。",
    "OLLAMA_PULL_NO_SUCCESS_STATUS": "模型拉取未返回 success 状态，请检查 Ollama 日志。",
    "OLLAMA_PULL_TIMEOUT": "模型拉取超时，请适当提高超时时间或稍后重试。",
    "OLLAMA_PULL_VERIFY_FAILED": "模型拉取完成后校验失败，模型可能尚未真正可用。",
    "SYSTEM_OLLAMA_PROVIDER_NOT_FOUND": "系统 Ollama 配置不存在，请先完成配置。",
}


def system_ollama_pull_failure_hint_for_code(code: str | None) -> str | None:
    if not code:
        return None
    return PULL_FAILURE_HINTS.get(code)


def get_system_ollama_pull_job(
    db: Session, *, pull_job_id: uuid.UUID
) -> SystemOllamaPullJob:
    job = db.get(SystemOllamaPullJob, pull_job_id)
    if job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="模型拉取任务不存在")
    return job


def list_system_ollama_pull_jobs(
    db: Session,
    *,
    provider_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int = 20,
) -> list[SystemOllamaPullJob]:
    safe_limit = min(max(1, int(limit)), 100)
    stmt = select(SystemOllamaPullJob).order_by(SystemOllamaPullJob.created_at.desc())
    if provider_id is not None:
        stmt = stmt.where(SystemOllamaPullJob.provider_id == provider_id)
    if active_only:
        stmt = stmt.where(SystemOllamaPullJob.status.in_(ACTIVE_PULL_STATUSES))
    return db.scalars(stmt.limit(safe_limit)).all()


def build_system_ollama_pull_payload(job: SystemOllamaPullJob) -> dict[str, object]:
    summary = dict(job.result_summary or {})
    progress = (
        summary.get("progress") if isinstance(summary.get("progress"), dict) else {}
    )
    progress_payload = {
        "phase": str(progress.get("phase") or "").strip() or None,
        "status_text": str(progress.get("status_text") or "").strip() or None,
        "percent": _safe_percent(progress.get("percent")),
        "completed": _to_non_negative_int(progress.get("completed")),
        "total": _to_non_negative_int(progress.get("total")),
        "digest": str(progress.get("digest") or "").strip() or None,
        "verified": bool(progress.get("verified")),
    }
    return {
        "id": job.id,
        "provider_id": job.provider_id,
        "model_name": job.model_name,
        "status": job.status,
        "stage": job.stage,
        "failure_code": job.failure_code,
        "failure_hint": job.failure_hint
        or system_ollama_pull_failure_hint_for_code(job.failure_code),
        "progress": progress_payload,
        "result_summary": summary,
        "created_by": job.created_by,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def trigger_system_ollama_pull_job(
    db: Session,
    *,
    provider: SystemAIProvider,
    name: str,
    created_by: uuid.UUID,
    request_id: str,
) -> tuple[SystemOllamaPullJob, bool, bool]:
    normalized_name = _normalize_model_name(name)
    if not provider.enabled:
        raise AppError(
            code="AI_PROVIDER_DISABLED",
            status_code=409,
            message="系统 Ollama 未启用",
        )

    active_job = _get_active_pull_job(db, provider_id=provider.id)
    if active_job is not None:
        if active_job.model_name == normalized_name:
            return active_job, True, False
        raise AppError(
            code="OLLAMA_PULL_ALREADY_RUNNING",
            status_code=409,
            message="当前已有其他模型拉取任务在执行",
            detail={
                "active_pull_job_id": str(active_job.id),
                "active_model_name": active_job.model_name,
            },
        )

    models = list_ollama_models(
        base_url=provider.base_url,
        timeout_seconds=int(provider.timeout_seconds),
    )
    resolved_model_name = _resolve_model_name(models, normalized_name)
    if resolved_model_name is not None:
        job = _create_pull_job(
            db,
            provider=provider,
            model_name=normalized_name,
            created_by=created_by,
            request_id=request_id,
        )
        _mark_pull_job_succeeded(
            db,
            job=job,
            provider=provider,
            model_name=resolved_model_name,
            request_id=request_id,
            pull_result={
                "event_count": 0,
                "success_status_received": False,
                "last_event": {},
            },
            verification={
                "verified": True,
                "model_count": len(models),
                "available_models": _model_names(models),
            },
            already_present=True,
        )
        return job, False, True

    job = _create_pull_job(
        db,
        provider=provider,
        model_name=normalized_name,
        created_by=created_by,
        request_id=request_id,
    )
    return job, False, False


def dispatch_system_ollama_pull_job(
    db: Session, *, job: SystemOllamaPullJob
) -> dict[str, Any]:
    from app.worker.tasks import enqueue_system_ollama_pull_job

    db.commit()
    db.refresh(job)

    bind = db.get_bind()
    bind_engine = getattr(bind, "engine", bind)
    task_id = enqueue_system_ollama_pull_job(pull_job_id=job.id, db_bind=bind_engine)
    if not task_id:
        raise AppError(
            code="OLLAMA_PULL_DISPATCH_FAILED",
            status_code=503,
            message="模型拉取任务派发失败",
        )

    dispatch_info = {"backend": "celery_or_local", "task_id": task_id}
    payload = {**(job.payload or {}), "dispatch": dispatch_info}
    db.execute(
        update(SystemOllamaPullJob)
        .where(SystemOllamaPullJob.id == job.id)
        .values(payload=payload, updated_at=utc_now())
    )
    job.payload = payload
    _append_pull_log(
        job=job,
        stage=job.stage,
        message=f"任务已投递执行队列，task_id={task_id}",
    )
    db.commit()
    return dispatch_info


def mark_system_ollama_pull_dispatch_failed(
    db: Session,
    *,
    pull_job_id: uuid.UUID,
    request_id: str,
    operator_user_id: uuid.UUID,
) -> None:
    job = db.get(SystemOllamaPullJob, pull_job_id)
    if job is None:
        return
    now = utc_now()
    job.status = SystemOllamaPullJobStatus.FAILED.value
    job.stage = SystemOllamaPullJobStage.PREPARE.value
    job.failure_code = "OLLAMA_PULL_DISPATCH_FAILED"
    job.failure_hint = system_ollama_pull_failure_hint_for_code(job.failure_code)
    job.finished_at = now
    if job.started_at is None:
        job.started_at = now
    _append_pull_log(
        job=job,
        stage=job.stage,
        message="任务派发失败: code=OLLAMA_PULL_DISPATCH_FAILED",
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="system.ai.ollama.model.pull.failed",
        resource_type="SYSTEM_OLLAMA_PULL_JOB",
        resource_id=str(job.id),
        result="FAILED",
        error_code=job.failure_code,
        detail_json={"model_name": job.model_name},
    )
    db.commit()


def run_system_ollama_pull_job(
    *, pull_job_id: uuid.UUID, db: Session | None = None
) -> None:
    owns_db = db is None
    session = db or SessionLocal()

    try:
        job = session.get(SystemOllamaPullJob, pull_job_id)
        if job is None:
            return
        if job.status in TERMINAL_PULL_STATUSES:
            return

        request_id = str((job.payload or {}).get("request_id") or "")
        provider = session.get(SystemAIProvider, job.provider_id)
        if provider is None:
            raise AppError(
                code="SYSTEM_OLLAMA_PROVIDER_NOT_FOUND",
                status_code=404,
                message="系统 Ollama 配置不存在",
            )
        if not provider.enabled:
            raise AppError(
                code="AI_PROVIDER_DISABLED",
                status_code=409,
                message="系统 Ollama 未启用",
            )

        model_name = _normalize_model_name(job.model_name)
        _set_pull_job_running(
            session, job=job, stage=SystemOllamaPullJobStage.PREPARE.value
        )
        _append_pull_log(
            job=job,
            stage=job.stage,
            message=f"开始准备拉取模型: {model_name}",
        )

        existing_models = list_ollama_models(
            base_url=provider.base_url,
            timeout_seconds=int(provider.timeout_seconds),
        )
        resolved_existing_model_name = _resolve_model_name(existing_models, model_name)
        if resolved_existing_model_name is not None:
            _set_pull_job_running(
                session, job=job, stage=SystemOllamaPullJobStage.VERIFY.value
            )
            _append_pull_log(
                job=job,
                stage=job.stage,
                message=f"模型已存在，跳过拉取并执行校验: {model_name}",
            )
            _set_pull_job_running(
                session,
                job=job,
                stage=SystemOllamaPullJobStage.FINALIZE.value,
            )
            _mark_pull_job_succeeded(
                session,
                job=job,
                provider=provider,
                model_name=resolved_existing_model_name,
                request_id=request_id,
                pull_result={
                    "event_count": 0,
                    "success_status_received": False,
                    "last_event": {},
                },
                verification={
                    "verified": True,
                    "model_count": len(existing_models),
                    "available_models": _model_names(existing_models),
                },
                already_present=True,
            )
            return

        _set_pull_job_running(
            session, job=job, stage=SystemOllamaPullJobStage.PULL.value
        )
        _append_pull_log(
            job=job,
            stage=job.stage,
            message=f"开始从 {provider.base_url} 拉取模型: {model_name}",
        )

        progress_state = {"status_text": None, "percent": None}

        def _on_event(event: dict[str, object]) -> None:
            _record_pull_progress(
                session,
                job=job,
                event=event,
                progress_state=progress_state,
            )

        pull_result = stream_ollama_model_pull(
            base_url=provider.base_url,
            name=model_name,
            timeout_seconds=max(int(provider.timeout_seconds), 300),
            on_event=_on_event,
        )

        _set_pull_job_running(
            session, job=job, stage=SystemOllamaPullJobStage.VERIFY.value
        )
        _append_pull_log(
            job=job,
            stage=job.stage,
            message=f"开始校验模型是否可用: {model_name}",
        )
        models = list_ollama_models(
            base_url=provider.base_url,
            timeout_seconds=int(provider.timeout_seconds),
        )
        resolved_model_name = _resolve_model_name(models, model_name)
        if resolved_model_name is None:
            raise AppError(
                code="OLLAMA_PULL_VERIFY_FAILED",
                status_code=502,
                message="模型拉取完成后未在 Ollama 模型列表中找到目标模型",
                detail={
                    "model_name": model_name,
                    "available_models": _model_names(models),
                },
            )

        _set_pull_job_running(
            session, job=job, stage=SystemOllamaPullJobStage.FINALIZE.value
        )
        _mark_pull_job_succeeded(
            session,
            job=job,
            provider=provider,
            model_name=resolved_model_name,
            request_id=request_id,
            pull_result={
                "event_count": pull_result.event_count,
                "success_status_received": pull_result.success_status_received,
                "last_event": pull_result.last_event,
            },
            verification={
                "verified": True,
                "model_count": len(models),
                "available_models": _model_names(models),
            },
            already_present=False,
        )
    except AppError as exc:
        session.rollback()
        job = session.get(SystemOllamaPullJob, pull_job_id)
        if job is not None:
            final_status = (
                SystemOllamaPullJobStatus.TIMEOUT.value
                if exc.code in PULL_TIMEOUT_CODES or exc.code.endswith("_TIMEOUT")
                else SystemOllamaPullJobStatus.FAILED.value
            )
            _fail_pull_job(
                session,
                job=job,
                failure_code=exc.code,
                request_id=str((job.payload or {}).get("request_id") or ""),
                detail=exc.detail,
                final_status=final_status,
            )
    except Exception as exc:
        session.rollback()
        job = session.get(SystemOllamaPullJob, pull_job_id)
        if job is not None:
            _fail_pull_job(
                session,
                job=job,
                failure_code="OLLAMA_PULL_INTERNAL_ERROR",
                request_id=str((job.payload or {}).get("request_id") or ""),
                detail={"error": str(exc)},
            )
    finally:
        if owns_db:
            session.close()


def _create_pull_job(
    db: Session,
    *,
    provider: SystemAIProvider,
    model_name: str,
    created_by: uuid.UUID,
    request_id: str,
) -> SystemOllamaPullJob:
    job = SystemOllamaPullJob(
        provider_id=provider.id,
        model_name=model_name,
        payload={
            "request_id": request_id,
            "provider_base_url": provider.base_url,
            "provider_timeout_seconds": int(provider.timeout_seconds),
        },
        status=SystemOllamaPullJobStatus.PENDING.value,
        stage=SystemOllamaPullJobStage.PREPARE.value,
        created_by=created_by,
        result_summary={
            "progress": {
                "phase": "prepare",
                "status_text": "等待执行",
                "percent": 0,
                "completed": None,
                "total": None,
                "digest": None,
                "verified": False,
            },
            "requested_model_name": model_name,
        },
    )
    db.add(job)
    db.flush()
    return job


def _get_active_pull_job(
    db: Session, *, provider_id: uuid.UUID
) -> SystemOllamaPullJob | None:
    return db.scalar(
        select(SystemOllamaPullJob)
        .where(
            SystemOllamaPullJob.provider_id == provider_id,
            SystemOllamaPullJob.status.in_(ACTIVE_PULL_STATUSES),
        )
        .order_by(SystemOllamaPullJob.created_at.desc())
        .limit(1)
    )


def _set_pull_job_running(db: Session, *, job: SystemOllamaPullJob, stage: str) -> None:
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.status = SystemOllamaPullJobStatus.RUNNING.value
    job.stage = stage
    job.failure_code = None
    job.failure_hint = None
    summary = dict(job.result_summary or {})
    progress = dict(summary.get("progress") or {})
    progress["phase"] = stage.lower()
    if stage == SystemOllamaPullJobStage.PREPARE.value:
        progress.setdefault("percent", 0)
        progress["status_text"] = "准备中"
    elif stage == SystemOllamaPullJobStage.VERIFY.value:
        progress["percent"] = max(99, _safe_percent(progress.get("percent")))
        progress["status_text"] = "校验模型可用性"
    elif stage == SystemOllamaPullJobStage.FINALIZE.value:
        progress["percent"] = 100
        progress["status_text"] = "写入最终状态"
    summary["progress"] = progress
    job.result_summary = summary
    db.commit()


def _record_pull_progress(
    db: Session,
    *,
    job: SystemOllamaPullJob,
    event: dict[str, object],
    progress_state: dict[str, object],
) -> None:
    summary = dict(job.result_summary or {})
    progress = dict(summary.get("progress") or {})

    status_text = str(event.get("status") or "").strip() or progress.get("status_text")
    percent = _safe_percent(event.get("percent"))
    completed = _to_non_negative_int(event.get("completed"))
    total = _to_non_negative_int(event.get("total"))
    digest = str(event.get("digest") or "").strip() or None

    progress.update(
        {
            "phase": "pull",
            "status_text": status_text,
            "percent": percent,
            "completed": completed,
            "total": total,
            "digest": digest,
            "verified": False,
        }
    )
    summary["progress"] = progress
    summary["event_count"] = int(summary.get("event_count") or 0) + 1
    summary["last_event"] = (
        dict(event.get("raw") or {}) if isinstance(event.get("raw"), dict) else {}
    )
    job.result_summary = summary
    db.commit()

    last_status = str(progress_state.get("status_text") or "") or None
    last_percent = _safe_percent(progress_state.get("percent"))
    should_log = False
    if status_text and status_text != last_status:
        should_log = True
    elif percent in {0, 100} and percent != last_percent:
        should_log = True
    elif (
        percent is not None and last_percent is not None and percent - last_percent >= 5
    ):
        should_log = True

    if should_log:
        suffix = ""
        if percent is not None:
            suffix = f", progress={percent}%"
        if completed is not None and total is not None and total > 0:
            suffix += f", bytes={completed}/{total}"
        _append_pull_log(
            job=job,
            stage=SystemOllamaPullJobStage.PULL.value,
            message=f"拉取进度: status={status_text or '-'}{suffix}",
        )

    progress_state["status_text"] = status_text
    progress_state["percent"] = percent


def _mark_pull_job_succeeded(
    db: Session,
    *,
    job: SystemOllamaPullJob,
    provider: SystemAIProvider,
    model_name: str,
    request_id: str,
    pull_result: dict[str, object],
    verification: dict[str, object],
    already_present: bool,
) -> None:
    _publish_model(provider=provider, model_name=model_name)
    now = utc_now()
    if job.started_at is None:
        job.started_at = now

    progress = {
        "phase": "finalize",
        "status_text": "模型可用",
        "percent": 100,
        "completed": _to_non_negative_int(
            (pull_result.get("last_event") or {}).get("completed")
            if isinstance(pull_result.get("last_event"), dict)
            else None
        ),
        "total": _to_non_negative_int(
            (pull_result.get("last_event") or {}).get("total")
            if isinstance(pull_result.get("last_event"), dict)
            else None
        ),
        "digest": str(
            ((pull_result.get("last_event") or {}).get("digest") or "")
            if isinstance(pull_result.get("last_event"), dict)
            else ""
        ).strip()
        or None,
        "verified": True,
    }

    job.status = SystemOllamaPullJobStatus.SUCCEEDED.value
    job.stage = SystemOllamaPullJobStage.FINALIZE.value
    job.failure_code = None
    job.failure_hint = None
    job.finished_at = now
    job.result_summary = {
        **(job.result_summary or {}),
        "progress": progress,
        "already_present": already_present,
        "pull_result": pull_result,
        "verification": verification,
        "published": True,
    }
    _append_pull_log(
        job=job,
        stage=SystemOllamaPullJobStage.FINALIZE.value,
        message=(
            f"模型拉取完成: model={model_name}, already_present={already_present}, "
            f"verified={bool(verification.get('verified'))}"
        ),
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=job.created_by,
        action="system.ai.ollama.model.pull.succeeded",
        resource_type="SYSTEM_OLLAMA_PULL_JOB",
        resource_id=str(job.id),
        result="SUCCEEDED",
        detail_json={
            "model_name": model_name,
            "already_present": already_present,
            "verified": bool(verification.get("verified")),
        },
    )
    db.commit()


def _fail_pull_job(
    db: Session,
    *,
    job: SystemOllamaPullJob,
    failure_code: str,
    request_id: str,
    detail: dict[str, object] | None = None,
    final_status: str = SystemOllamaPullJobStatus.FAILED.value,
) -> None:
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.status = final_status
    job.failure_code = failure_code
    job.failure_hint = system_ollama_pull_failure_hint_for_code(failure_code)
    job.finished_at = now
    summary = dict(job.result_summary or {})
    progress = dict(summary.get("progress") or {})
    progress["status_text"] = (
        "任务超时"
        if final_status == SystemOllamaPullJobStatus.TIMEOUT.value
        else "任务失败"
    )
    progress["verified"] = False
    summary["progress"] = progress
    if detail:
        summary["failure_detail"] = detail
    job.result_summary = summary
    label = (
        "任务超时"
        if final_status == SystemOllamaPullJobStatus.TIMEOUT.value
        else "任务失败"
    )
    _append_pull_log(
        job=job,
        stage=job.stage,
        message=f"{label}: code={failure_code}",
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=job.created_by,
        action="system.ai.ollama.model.pull.failed",
        resource_type="SYSTEM_OLLAMA_PULL_JOB",
        resource_id=str(job.id),
        result=final_status,
        error_code=failure_code,
        detail_json={"model_name": job.model_name, **(detail or {})},
    )
    db.commit()


def _publish_model(*, provider: SystemAIProvider, model_name: str) -> None:
    models = _normalized_model_list(provider.published_models_json)
    if model_name not in models:
        models.append(model_name)
        provider.published_models_json = models
    if not provider.default_model:
        provider.default_model = model_name


def _append_pull_log(*, job: SystemOllamaPullJob, stage: str, message: str) -> None:
    append_task_log(
        task_type=TaskLogType.OLLAMA_PULL.value,
        task_id=job.id,
        stage=stage,
        message=message,
        project_id=None,
    )


def _model_exists(models: list[dict[str, object]], model_name: str) -> bool:
    return _resolve_model_name(models, model_name) is not None


def _resolve_model_name(models: list[dict[str, object]], model_name: str) -> str | None:
    target = _canonicalize_model_name(model_name)
    for candidate in _model_names(models):
        if _canonicalize_model_name(candidate) == target:
            return candidate
    return None


def _model_names(models: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for item in models:
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _normalize_model_name(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="模型名称不能为空",
        )
    return normalized


def _canonicalize_model_name(value: object) -> str:
    normalized = _normalize_model_name(value)
    if "@" in normalized:
        return normalized
    tail = normalized.rsplit("/", 1)[-1]
    if ":" in tail:
        return normalized
    return f"{normalized}:latest"


def _normalized_model_list(values: object) -> list[str]:
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


def _safe_percent(value: object) -> int:
    parsed = _to_non_negative_int(value)
    if parsed is None:
        return 0
    return max(0, min(100, parsed))


def _to_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
