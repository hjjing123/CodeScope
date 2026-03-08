from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    Finding,
    FindingSeverity,
    FindingStatus,
    Job,
    JobFailureCategory,
    JobStage,
    JobStatus,
    JobType,
    Project,
    ScanMode,
    TaskLogType,
    Version,
    VersionStatus,
    utc_now,
)
from app.services.audit_service import append_audit_log
from app.services.rule_file_service import get_rules_by_keys, normalize_rule_selector
from app.services.scan_external import run_external_scan as run_external_scan_pipeline
from app.services.task_log_service import append_task_log


RETRYABLE_SCAN_STATUSES = {
    JobStatus.FAILED.value,
    JobStatus.CANCELED.value,
    JobStatus.TIMEOUT.value,
}

TERMINAL_SCAN_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELED.value,
    JobStatus.TIMEOUT.value,
}

SCAN_FAILURE_HINTS: dict[str, str] = {
    "VERSION_NOT_READY": "请先确保目标版本处于 READY 状态。",
    "SCAN_EXTERNAL_NOT_CONFIGURED": "请配置外部扫描命令与结果目录，或切换到 stub 引擎。",
    "SCAN_EXTERNAL_RUN_FAILED": "外部扫描执行失败，请检查执行日志和环境依赖。",
    "SCAN_EXTERNAL_RUN_TIMEOUT": "外部扫描执行超时，请检查执行耗时与超时配置。",
    "SCAN_EXTERNAL_JOERN_FAILED": "Joern 导出阶段失败，请检查 Joern 配置、脚本与输入。",
    "SCAN_EXTERNAL_JOERN_TIMEOUT": "Joern 导出阶段超时，请检查工程规模与超时配置。",
    "SCAN_EXTERNAL_IMPORT_FAILED": "Neo4j 导入阶段失败，请检查导入脚本与数据库状态。",
    "SCAN_EXTERNAL_IMPORT_TIMEOUT": "Neo4j 导入阶段超时，请检查导入规模与超时配置。",
    "SCAN_EXTERNAL_POST_LABELS_FAILED": "语义增强阶段失败，请检查 post_labels 脚本。",
    "SCAN_EXTERNAL_POST_LABELS_TIMEOUT": "语义增强阶段超时，请检查脚本复杂度与超时配置。",
    "SCAN_EXTERNAL_RULES_FAILED": "规则执行阶段失败，请检查规则脚本与查询环境。",
    "SCAN_EXTERNAL_RULES_TIMEOUT": "规则执行阶段超时，请检查规则复杂度与超时配置。",
    "SCAN_EXTERNAL_RESULT_MISSING": "外部扫描未产出结果文件，请检查 pipeline 输出目录。",
    "SCAN_EXTERNAL_RESULT_INVALID": "外部扫描结果格式异常，请检查 round_*.json 与 summary.json。",
    "SCAN_DISPATCH_FAILED": "任务派发失败，请检查 Celery/Redis 配置后重试。",
    "SCAN_CANCELED": "任务已取消，可按需重试。",
    "SCAN_INTERNAL_ERROR": "扫描执行异常，请稍后重试。",
}

STAGE_SEQUENCE = [
    JobStage.PREPARE.value,
    JobStage.ANALYZE.value,
    JobStage.QUERY.value,
    JobStage.AGGREGATE.value,
    JobStage.AI.value,
    JobStage.CLEANUP.value,
]

FAILURE_CATEGORY_BY_CODE: dict[str, str] = {
    "VERSION_NOT_READY": JobFailureCategory.INPUT.value,
    "SCAN_EXTERNAL_NOT_CONFIGURED": JobFailureCategory.ENV.value,
    "SCAN_EXTERNAL_RUN_FAILED": JobFailureCategory.ENGINE.value,
    "SCAN_EXTERNAL_RUN_TIMEOUT": JobFailureCategory.RESOURCE.value,
    "SCAN_EXTERNAL_JOERN_FAILED": JobFailureCategory.ENGINE.value,
    "SCAN_EXTERNAL_JOERN_TIMEOUT": JobFailureCategory.RESOURCE.value,
    "SCAN_EXTERNAL_IMPORT_FAILED": JobFailureCategory.ENGINE.value,
    "SCAN_EXTERNAL_IMPORT_TIMEOUT": JobFailureCategory.RESOURCE.value,
    "SCAN_EXTERNAL_POST_LABELS_FAILED": JobFailureCategory.RULE.value,
    "SCAN_EXTERNAL_POST_LABELS_TIMEOUT": JobFailureCategory.RESOURCE.value,
    "SCAN_EXTERNAL_RULES_FAILED": JobFailureCategory.RULE.value,
    "SCAN_EXTERNAL_RULES_TIMEOUT": JobFailureCategory.RESOURCE.value,
    "SCAN_EXTERNAL_RESULT_MISSING": JobFailureCategory.STORAGE.value,
    "SCAN_EXTERNAL_RESULT_INVALID": JobFailureCategory.ENGINE.value,
    "SCAN_DISPATCH_FAILED": JobFailureCategory.ENV.value,
    "SCAN_CANCELED": JobFailureCategory.SYSTEM.value,
    "SCAN_INTERNAL_ERROR": JobFailureCategory.SYSTEM.value,
}

TIMEOUT_FAILURE_CODES = {
    "SCAN_EXTERNAL_RUN_TIMEOUT",
    "SCAN_EXTERNAL_JOERN_TIMEOUT",
    "SCAN_EXTERNAL_IMPORT_TIMEOUT",
    "SCAN_EXTERNAL_POST_LABELS_TIMEOUT",
    "SCAN_EXTERNAL_RULES_TIMEOUT",
}


@dataclass(slots=True)
class ScanExecutionResult:
    findings: list[dict[str, str]]
    result_summary: dict[str, object]


def failure_hint_for_code(failure_code: str | None) -> str | None:
    if failure_code is None:
        return None
    return SCAN_FAILURE_HINTS.get(failure_code)


def failure_category_for_code(failure_code: str | None, *, default: str) -> str:
    if not failure_code:
        return default
    return FAILURE_CATEGORY_BY_CODE.get(failure_code, default)


def normalize_scan_mode(value: str) -> str:
    normalized = value.strip().upper()
    valid = {item.value for item in ScanMode}
    if normalized not in valid:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="scan_mode 仅支持 FULL/FAST/VERIFY",
            detail={"allowed_values": sorted(valid)},
        )
    return normalized


def normalize_rule_keys(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        raw = (item or "").strip()
        if not raw:
            continue
        try:
            rule = normalize_rule_selector(raw)
        except AppError as exc:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="rule_keys 中存在非法规则名",
                detail={"rule": raw},
            ) from exc

        marker = rule.lower()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(rule)
    return cleaned


def compute_scan_request_fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def get_existing_idempotent_scan_job(
    db: Session,
    *,
    project_id: uuid.UUID,
    idempotency_key: str | None,
    request_fingerprint: str,
) -> Job | None:
    normalized_key = (idempotency_key or "").strip()
    if not normalized_key:
        return None

    existing = db.scalar(
        select(Job).where(
            Job.project_id == project_id,
            Job.job_type == JobType.SCAN.value,
            Job.idempotency_key == normalized_key,
        )
    )
    if existing is None:
        return None

    if (
        existing.request_fingerprint is not None
        and existing.request_fingerprint != request_fingerprint
    ):
        raise AppError(
            code="IDEMPOTENCY_KEY_REUSED",
            status_code=409,
            message="同一个 Idempotency-Key 不能用于不同参数请求",
        )
    return existing


def create_scan_job(
    db: Session,
    *,
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: dict[str, object],
    created_by: uuid.UUID,
    idempotency_key: str | None,
    request_fingerprint: str,
) -> Job:
    job = Job(
        project_id=project_id,
        version_id=version_id,
        job_type=JobType.SCAN.value,
        payload=payload,
        idempotency_key=(idempotency_key or "").strip() or None,
        request_fingerprint=request_fingerprint,
        status=JobStatus.PENDING.value,
        stage=JobStage.PREPARE.value,
        created_by=created_by,
        result_summary={},
    )
    db.add(job)
    db.flush()
    return job


def dispatch_scan_job(db: Session, *, job: Job) -> dict[str, Any]:
    settings = get_settings()
    backend = (settings.scan_dispatch_backend or "sync").strip().lower()
    allow_fallback = bool(settings.scan_dispatch_fallback_to_sync)

    if backend == "celery":
        try:
            from app.worker.tasks import enqueue_scan_job

            task_id = enqueue_scan_job(job_id=job.id)
            if task_id:
                dispatch_info: dict[str, Any] = {
                    "backend": "celery",
                    "task_id": task_id,
                    "requested_backend": "celery",
                }
                _persist_dispatch_info(db, job=job, dispatch_info=dispatch_info)
                _append_scan_log(
                    job_id=job.id,
                    stage=JobStage.PREPARE.value,
                    message=f"任务已投递到 Celery 队列，task_id={task_id}",
                )
                return dispatch_info

            if not allow_fallback:
                raise AppError(
                    code="SCAN_DISPATCH_FAILED",
                    status_code=503,
                    message="任务派发失败",
                    detail={"reason": "celery_unavailable"},
                )

            dispatch_info = {
                "backend": "sync",
                "task_id": None,
                "requested_backend": "celery",
                "fallback_reason": "celery_unavailable",
            }
            _persist_dispatch_info(db, job=job, dispatch_info=dispatch_info)
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.PREPARE.value,
                message="Celery 不可用，已回退为同步执行。",
            )
            run_scan_job(job_id=job.id, db=db)
            return dispatch_info
        except Exception as exc:
            if not allow_fallback:
                raise AppError(
                    code="SCAN_DISPATCH_FAILED",
                    status_code=503,
                    message="任务派发失败",
                    detail={"reason": str(exc)},
                ) from exc

            dispatch_info = {
                "backend": "sync",
                "task_id": None,
                "requested_backend": "celery",
                "fallback_reason": str(exc),
            }
            _persist_dispatch_info(db, job=job, dispatch_info=dispatch_info)
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.PREPARE.value,
                message=f"Celery 派发异常，已回退同步执行: {exc}",
            )
            run_scan_job(job_id=job.id, db=db)
            return dispatch_info

    dispatch_info = {
        "backend": "sync",
        "task_id": None,
        "requested_backend": backend,
    }
    _persist_dispatch_info(db, job=job, dispatch_info=dispatch_info)
    _append_scan_log(
        job_id=job.id,
        stage=JobStage.PREPARE.value,
        message="任务以同步模式执行。",
    )
    run_scan_job(job_id=job.id, db=db)
    return dispatch_info


def read_scan_job_logs(
    *, job_id: uuid.UUID, stage: str | None, tail: int
) -> list[dict[str, Any]]:
    safe_tail = min(max(1, tail), 5000)
    stages: list[str]
    if stage is None:
        stages = list(STAGE_SEQUENCE)
    else:
        normalized = stage.strip().lower()
        resolved: str | None = None
        for candidate in STAGE_SEQUENCE:
            if candidate.lower() == normalized:
                resolved = candidate
                break
        if resolved is None:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="stage 参数不合法",
                detail={"allowed_stages": STAGE_SEQUENCE},
            )
        stages = [resolved]

    items: list[dict[str, Any]] = []
    for stage_name in stages:
        path = _stage_log_path(job_id=job_id, stage=stage_name)
        if not path.exists() or not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        line_count = len(lines)
        truncated = line_count > safe_tail
        items.append(
            {
                "stage": stage_name,
                "lines": lines[-safe_tail:],
                "line_count": line_count,
                "truncated": truncated,
            }
        )
    return items


def _persist_dispatch_info(
    db: Session, *, job: Job, dispatch_info: dict[str, Any]
) -> None:
    refreshed = db.get(Job, job.id)
    if refreshed is None:
        return
    refreshed.payload = {**(refreshed.payload or {}), "dispatch": dispatch_info}
    db.commit()


def _job_log_dir(*, job_id: uuid.UUID) -> Path:
    path = Path(get_settings().scan_log_root) / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_log_path(*, job_id: uuid.UUID, stage: str) -> Path:
    safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", stage).strip("_") or "unknown"
    return _job_log_dir(job_id=job_id) / f"{safe_stage}.log"


def _append_scan_log(
    *,
    job_id: uuid.UUID,
    stage: str,
    message: str,
    project_id: uuid.UUID | None = None,
) -> None:
    append_task_log(
        task_type=TaskLogType.SCAN.value,
        task_id=job_id,
        stage=stage,
        message=message,
        project_id=project_id,
    )


def cancel_scan_job(
    db: Session,
    *,
    job: Job,
    request_id: str,
    operator_user_id: uuid.UUID,
) -> Job:
    if job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="仅支持取消扫描任务"
        )

    if job.status in TERMINAL_SCAN_STATUSES:
        raise AppError(
            code="JOB_NOT_CANCELABLE", status_code=409, message="当前任务状态不允许取消"
        )

    now = utc_now()
    job.status = JobStatus.CANCELED.value
    job.stage = JobStage.CLEANUP.value
    job.failure_code = "SCAN_CANCELED"
    job.failure_stage = job.stage
    job.failure_category = JobFailureCategory.SYSTEM.value
    job.failure_hint = failure_hint_for_code("SCAN_CANCELED")
    job.finished_at = now
    if job.started_at is None:
        job.started_at = now
    job.result_summary = {**(job.result_summary or {}), "canceled": True}
    _append_scan_log(
        job_id=job.id,
        stage=job.stage,
        message="任务已取消。",
        project_id=job.project_id,
    )

    dispatch = job.payload.get("dispatch") if isinstance(job.payload, dict) else None
    if isinstance(dispatch, dict):
        task_id = dispatch.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            try:
                from app.worker.tasks import revoke_scan_job

                revoked = revoke_scan_job(task_id=task_id)
                if revoked:
                    _append_scan_log(
                        job_id=job.id,
                        stage=job.stage,
                        message=f"已请求撤销 Celery 任务: {task_id}",
                    )
            except Exception:
                _append_scan_log(
                    job_id=job.id,
                    stage=job.stage,
                    message=f"撤销 Celery 任务失败: {task_id}",
                )

    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="scan.canceled",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        detail_json={"job_type": job.job_type},
    )
    db.commit()
    db.refresh(job)
    return job


def clone_scan_job_for_retry(
    db: Session,
    *,
    source_job: Job,
    request_id: str,
    created_by: uuid.UUID,
) -> Job:
    if source_job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="仅支持重试扫描任务"
        )

    if source_job.status not in RETRYABLE_SCAN_STATUSES:
        raise AppError(
            code="JOB_NOT_RETRYABLE", status_code=409, message="当前任务状态不允许重试"
        )

    retry_payload = {
        **source_job.payload,
        "request_id": request_id,
        "retry_of_job_id": str(source_job.id),
    }
    retried_job = Job(
        project_id=source_job.project_id,
        version_id=source_job.version_id,
        job_type=JobType.SCAN.value,
        payload=retry_payload,
        idempotency_key=None,
        request_fingerprint=None,
        status=JobStatus.PENDING.value,
        stage=JobStage.PREPARE.value,
        created_by=created_by,
        result_summary={},
    )
    db.add(retried_job)
    db.flush()
    return retried_job


def run_scan_job(*, job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return
        if job.job_type != JobType.SCAN.value:
            return
        if job.status in TERMINAL_SCAN_STATUSES:
            return

        request_id = str(job.payload.get("request_id", ""))
        project = session.get(Project, job.project_id)
        if project is None:
            _fail_scan_job(
                session,
                job=job,
                stage=JobStage.PREPARE.value,
                failure_code="NOT_FOUND",
                failure_category=JobFailureCategory.INPUT.value,
                request_id=request_id,
            )
            return

        version = session.get(Version, job.version_id)
        if version is None or version.project_id != project.id:
            _fail_scan_job(
                session,
                job=job,
                stage=JobStage.PREPARE.value,
                failure_code="NOT_FOUND",
                failure_category=JobFailureCategory.INPUT.value,
                request_id=request_id,
            )
            return
        if version.status != VersionStatus.READY.value:
            _fail_scan_job(
                session,
                job=job,
                stage=JobStage.PREPARE.value,
                failure_code="VERSION_NOT_READY",
                failure_category=JobFailureCategory.INPUT.value,
                request_id=request_id,
            )
            return

        _set_scan_job_running(session, job=job, stage=JobStage.PREPARE.value)
        _set_scan_job_running(session, job=job, stage=JobStage.ANALYZE.value)
        _set_scan_job_running(session, job=job, stage=JobStage.QUERY.value)

        engine_mode = (get_settings().scan_engine_mode or "stub").strip().lower()
        if engine_mode == "external":
            execution = _run_external_scan(job=job)
        else:
            execution = _run_stub_scan(job=job)

        _set_scan_job_running(session, job=job, stage=JobStage.AGGREGATE.value)
        rule_keys: set[str] = set()
        for item in execution.findings:
            raw_rule_key = str(item.get("rule_key") or "").strip()
            if not raw_rule_key:
                continue
            try:
                rule_keys.add(normalize_rule_selector(raw_rule_key))
            except AppError:
                rule_keys.add(raw_rule_key)
        rule_meta_by_key = get_rules_by_keys(rule_keys)

        for finding_data in execution.findings:
            raw_rule_key = str(finding_data.get("rule_key") or "").strip()
            if not raw_rule_key:
                continue
            try:
                rule_key = normalize_rule_selector(raw_rule_key)
            except AppError:
                rule_key = raw_rule_key
            meta = rule_meta_by_key.get(rule_key)
            fallback_path = str(finding_data.get("file_path") or "").strip() or None
            source_file = str(finding_data.get("source_file") or "").strip() or None
            sink_file = str(finding_data.get("sink_file") or "").strip() or None
            if fallback_path is None:
                fallback_path = sink_file or source_file

            evidence_json = _normalize_evidence_payload(
                finding_data.get("evidence_json") or finding_data.get("evidence")
            )
            session.add(
                Finding(
                    project_id=job.project_id,
                    version_id=job.version_id,
                    job_id=job.id,
                    rule_key=rule_key,
                    rule_version=_to_int(
                        finding_data.get("rule_version"),
                        default=meta.active_version if meta is not None else None,
                    ),
                    vuln_type=(
                        str(finding_data.get("vuln_type") or "").strip()
                        or (meta.vuln_type if meta is not None else None)
                    ),
                    severity=str(
                        finding_data.get("severity") or FindingSeverity.MED.value
                    ),
                    status=FindingStatus.OPEN.value,
                    file_path=fallback_path,
                    line_start=_to_int(finding_data.get("line_start")),
                    line_end=_to_int(finding_data.get("line_end")),
                    has_path=bool(finding_data.get("has_path", False)),
                    path_length=_to_int(finding_data.get("path_length")),
                    source_file=source_file,
                    source_line=_to_int(finding_data.get("source_line")),
                    sink_file=sink_file,
                    sink_line=_to_int(finding_data.get("sink_line")),
                    evidence_json=evidence_json,
                )
            )

        _set_scan_job_running(session, job=job, stage=JobStage.CLEANUP.value)
        job.status = JobStatus.SUCCEEDED.value
        job.failure_code = None
        job.failure_stage = None
        job.failure_category = None
        job.failure_hint = None
        job.finished_at = utc_now()
        job.result_summary = execution.result_summary
        _append_scan_log(
            job_id=job.id,
            stage=JobStage.CLEANUP.value,
            message=f"任务成功，发现 {execution.result_summary.get('total_findings', 0)} 条结果",
            project_id=job.project_id,
        )

        append_audit_log(
            session,
            request_id=request_id,
            operator_user_id=job.created_by,
            action="scan.succeeded",
            resource_type="JOB",
            resource_id=str(job.id),
            project_id=job.project_id,
            detail_json={
                "engine_mode": execution.result_summary.get("engine_mode", "stub"),
                "total_findings": execution.result_summary.get("total_findings", 0),
            },
        )
        session.commit()

        try:
            from app.services.rule_stats_service import dispatch_rule_stats_aggregation

            task_id = dispatch_rule_stats_aggregation(session, job_id=job.id)
            if task_id:
                _append_scan_log(
                    job_id=job.id,
                    stage=JobStage.CLEANUP.value,
                    message=f"已投递规则统计聚合任务: {task_id}",
                )
        except Exception as exc:
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.CLEANUP.value,
                message=f"规则统计聚合派发失败（不影响扫描结果）: {exc}",
            )
    except AppError as exc:
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None:
            is_timeout = exc.code in TIMEOUT_FAILURE_CODES or exc.code.endswith(
                "_TIMEOUT"
            )
            final_status = (
                JobStatus.TIMEOUT.value if is_timeout else JobStatus.FAILED.value
            )
            _fail_scan_job(
                session,
                job=job,
                stage=job.stage,
                failure_code=exc.code,
                failure_category=failure_category_for_code(
                    exc.code,
                    default=JobFailureCategory.ENGINE.value,
                ),
                request_id=str(job.payload.get("request_id", "")),
                detail=exc.detail,
                final_status=final_status,
            )
    except Exception:
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None:
            _fail_scan_job(
                session,
                job=job,
                stage=job.stage,
                failure_code="SCAN_INTERNAL_ERROR",
                failure_category=JobFailureCategory.SYSTEM.value,
                request_id=str(job.payload.get("request_id", "")),
            )
    finally:
        if owns_db:
            session.close()


def _set_scan_job_running(db: Session, *, job: Job, stage: str) -> None:
    if job.started_at is None:
        job.started_at = utc_now()
    job.status = JobStatus.RUNNING.value
    job.stage = stage
    job.failure_code = None
    job.failure_stage = None
    job.failure_category = None
    job.failure_hint = None
    _append_scan_log(
        job_id=job.id,
        stage=stage,
        message=f"进入阶段 {stage}",
        project_id=job.project_id,
    )
    db.commit()


def _fail_scan_job(
    db: Session,
    *,
    job: Job,
    stage: str,
    failure_code: str,
    failure_category: str,
    request_id: str,
    detail: dict[str, object] | None = None,
    final_status: str = JobStatus.FAILED.value,
) -> None:
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.status = final_status
    job.stage = stage
    job.failure_code = failure_code
    job.failure_stage = stage
    job.failure_category = failure_category
    job.failure_hint = failure_hint_for_code(failure_code)
    job.finished_at = now
    failure_label = (
        "任务超时" if final_status == JobStatus.TIMEOUT.value else "任务失败"
    )
    _append_scan_log(
        job_id=job.id,
        stage=stage,
        message=f"{failure_label}: code={failure_code}, category={failure_category}",
        project_id=job.project_id,
    )

    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=job.created_by,
        action="scan.failed",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        result=final_status,
        error_code=failure_code,
        detail_json=detail or {},
    )
    db.commit()


def _run_stub_scan(*, job: Job) -> ScanExecutionResult:
    scan_mode = normalize_scan_mode(
        str(job.payload.get("scan_mode", ScanMode.FULL.value))
    )
    target_rule_id = str(job.payload.get("target_rule_id") or "").strip()
    resolved_rule_keys = normalize_rule_keys(
        list(job.payload.get("resolved_rule_keys") or [])
    )
    direct_rule_keys = normalize_rule_keys(list(job.payload.get("rule_keys") or []))
    rule_keys = resolved_rule_keys or direct_rule_keys
    _append_scan_log(
        job_id=job.id,
        stage=JobStage.QUERY.value,
        message=(
            f"stub 执行: mode={scan_mode}, rule_count={len(rule_keys)}, "
            f"target_rule_id={target_rule_id or '-'}"
        ),
    )

    findings: list[dict[str, str]] = []
    if scan_mode == ScanMode.VERIFY.value:
        rule_key = target_rule_id or (
            rule_keys[0] if rule_keys else "focused.snapshot.check"
        )
        findings.append({"rule_key": rule_key, "severity": FindingSeverity.MED.value})
    elif scan_mode == ScanMode.FAST.value:
        seeds = rule_keys[:2] if rule_keys else ["fast.input.validation"]
        for rule_key in seeds:
            findings.append(
                {"rule_key": rule_key, "severity": FindingSeverity.LOW.value}
            )
    else:
        seeds = (
            rule_keys[:3]
            if rule_keys
            else [
                "stub.any_any_xss",
                "stub.any_any_urlredirect",
                "stub.asterisk_alloworigin_cors",
            ]
        )
        severities = [
            FindingSeverity.HIGH.value,
            FindingSeverity.MED.value,
            FindingSeverity.LOW.value,
        ]
        for idx, rule_key in enumerate(seeds):
            findings.append(
                {"rule_key": rule_key, "severity": severities[idx % len(severities)]}
            )

    result_summary = _build_result_summary(
        findings=findings,
        scan_mode=scan_mode,
        engine_mode="stub",
        extra={
            "total_rules": len(rule_keys) if rule_keys else len(findings),
            "total_rows": len(findings),
            "partial_failures": [],
        },
    )
    _append_scan_log(
        job_id=job.id,
        stage=JobStage.AGGREGATE.value,
        message=f"stub 结果汇总完成: findings={len(findings)}",
    )
    return ScanExecutionResult(findings=findings, result_summary=result_summary)


def _run_external_scan(*, job: Job) -> ScanExecutionResult:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    scan_mode = normalize_scan_mode(
        str(job.payload.get("scan_mode", ScanMode.FULL.value))
    )

    external_result = run_external_scan_pipeline(
        job=job,
        settings=settings,
        backend_root=backend_root,
        append_log=lambda stage, message: _append_scan_log(
            job_id=job.id, stage=stage, message=message
        ),
        severity_from_rule_key=_severity_from_rule_key,
    )

    result_summary = _build_result_summary(
        findings=external_result.findings,
        scan_mode=scan_mode,
        engine_mode="external",
        extra=external_result.summary_extra,
    )
    _append_scan_log(
        job_id=job.id,
        stage=JobStage.AGGREGATE.value,
        message=(
            f"external 结果汇总完成: findings={len(external_result.findings)}, "
            f"hit_rules={result_summary.get('hit_rules', 0)}"
        ),
    )
    return ScanExecutionResult(
        findings=external_result.findings, result_summary=result_summary
    )


def _build_result_summary(
    *,
    findings: list[dict[str, str]],
    scan_mode: str,
    engine_mode: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    severity_counts = {
        FindingSeverity.HIGH.value: 0,
        FindingSeverity.MED.value: 0,
        FindingSeverity.LOW.value: 0,
    }
    hit_rules: set[str] = set()
    for item in findings:
        severity = item["severity"]
        if severity in severity_counts:
            severity_counts[severity] += 1
        hit_rules.add(item["rule_key"])

    summary: dict[str, object] = {
        "engine_mode": engine_mode,
        "scan_mode": scan_mode,
        "total_findings": len(findings),
        "severity_counts": severity_counts,
        "hit_rule_count": len(hit_rules),
        "partial_failures": [],
    }
    if extra:
        summary.update(extra)
    return summary


def _to_int(value: object, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_evidence_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return {
            "items": [
                item
                for item in value
                if isinstance(item, (dict, str, int, float, bool))
            ]
        }
    return {}


def _severity_from_rule_key(rule_key: str) -> str:
    key = rule_key.lower()
    if any(
        token in key
        for token in ["rce", "cmdi", "deserialization", "sqli", "sql", "xxe"]
    ):
        return FindingSeverity.HIGH.value
    if any(
        token in key for token in ["xss", "ssrf", "upload", "pathtraver", "redirect"]
    ):
        return FindingSeverity.MED.value
    return FindingSeverity.LOW.value
