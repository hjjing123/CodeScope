from __future__ import annotations

import uuid
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    SelfTestJob,
    SelfTestJobStage,
    SelfTestJobStatus,
    TaskLogType,
    Version,
    VersionStatus,
    utc_now,
)
from app.services.audit_service import append_audit_log
from app.services.rule_file_service import (
    resolve_rule_content as resolve_file_rule_content,
)
from app.services.rule_validation_service import validate_rule_content_for_publish
from app.services.scan_external.neo4j_runner import split_cypher_statements
from app.services.task_log_service import append_task_log


SELFTEST_TIMEOUT_CODES = {"RULE_TIMEOUT"}

SELFTEST_FAILURE_HINTS: dict[str, str] = {
    "RULE_DRAFT_NOT_FOUND": "未找到可用规则草稿，请先创建或指定规则版本。",
    "RULE_VERSION_NOT_FOUND": "指定规则版本不存在。",
    "RULE_NOT_FOUND": "规则不存在。",
    "VERSION_NOT_READY": "目标版本未就绪，请选择 READY 版本。",
    "ARCHIVE_INVALID": "上传归档无效，请检查 zip/tar.gz 文件。",
    "RULE_TIMEOUT": "规则自测执行超时，请缩小查询范围或提高超时时间。",
    "SELFTEST_DISPATCH_FAILED": "规则自测派发失败，请检查调度器配置。",
    "SELFTEST_INTERNAL_ERROR": "规则自测执行异常，请稍后重试。",
}


def selftest_failure_hint_for_code(code: str | None) -> str | None:
    if not code:
        return None
    return SELFTEST_FAILURE_HINTS.get(code)


def create_selftest_job(
    db: Session,
    *,
    rule_key: str | None,
    rule_version: int | None,
    payload: dict[str, object],
    created_by: uuid.UUID,
) -> SelfTestJob:
    job = SelfTestJob(
        rule_key=(rule_key or "").strip() or None,
        rule_version=rule_version,
        payload=payload,
        status=SelfTestJobStatus.PENDING.value,
        stage=SelfTestJobStage.PREPARE.value,
        created_by=created_by,
        result_summary={},
    )
    db.add(job)
    db.flush()
    return job


def dispatch_selftest_job(db: Session, *, job: SelfTestJob) -> dict[str, Any]:
    from app.worker.tasks import enqueue_rule_selftest_job

    bind = db.get_bind()
    bind_engine = getattr(bind, "engine", bind)
    task_id = enqueue_rule_selftest_job(selftest_job_id=job.id, db_bind=bind_engine)
    if not task_id:
        raise AppError(
            code="SELFTEST_DISPATCH_FAILED",
            status_code=503,
            message="规则自测任务派发失败",
        )

    dispatch_info = {"backend": "celery_or_local", "task_id": task_id}
    refreshed = db.get(SelfTestJob, job.id)
    if refreshed is not None:
        refreshed.payload = {**(refreshed.payload or {}), "dispatch": dispatch_info}
        _append_selftest_log(
            job=refreshed,
            stage=refreshed.stage,
            message=f"任务已投递执行队列，task_id={task_id}",
        )
        db.commit()
    return dispatch_info


def mark_selftest_dispatch_failed(
    db: Session,
    *,
    job_id: uuid.UUID,
    request_id: str,
    operator_user_id: uuid.UUID,
) -> None:
    job = db.get(SelfTestJob, job_id)
    if job is None:
        return
    job.status = SelfTestJobStatus.FAILED.value
    job.stage = SelfTestJobStage.PREPARE.value
    job.failure_code = "SELFTEST_DISPATCH_FAILED"
    job.failure_hint = selftest_failure_hint_for_code(job.failure_code)
    job.finished_at = utc_now()
    if job.started_at is None:
        job.started_at = job.finished_at
    _append_selftest_log(
        job=job,
        stage=job.stage,
        message="任务派发失败: code=SELFTEST_DISPATCH_FAILED",
    )

    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="rule.selftest.dispatch.failed",
        resource_type="SELFTEST_JOB",
        resource_id=str(job_id),
        result="FAILED",
        error_code="SELFTEST_DISPATCH_FAILED",
    )
    db.commit()


def run_selftest_job(*, selftest_job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()

    try:
        job = session.get(SelfTestJob, selftest_job_id)
        if job is None:
            return
        if job.status in {
            SelfTestJobStatus.SUCCEEDED.value,
            SelfTestJobStatus.FAILED.value,
            SelfTestJobStatus.CANCELED.value,
            SelfTestJobStatus.TIMEOUT.value,
        }:
            return

        payload = job.payload if isinstance(job.payload, dict) else {}
        request_id = str(payload.get("request_id") or "")

        _set_selftest_running(session, job=job, stage=SelfTestJobStage.PREPARE.value)
        rule_key, rule_version, content = _resolve_rule_content(session, job=job)

        _set_selftest_running(session, job=job, stage=SelfTestJobStage.EXECUTE.value)
        target_info = _resolve_target(session, payload=payload)
        query_text = str(content.get("query") or "")
        timeout_ms = int(content.get("timeout_ms") or 0)
        statements = split_cypher_statements(query_text)

        estimated_ms = max(
            10, len(statements) * 120 + int(target_info["source_file_count"]) * 5
        )
        if timeout_ms > 0 and estimated_ms > timeout_ms:
            raise AppError(
                code="RULE_TIMEOUT",
                status_code=422,
                message="规则自测执行超时",
                detail={"estimated_ms": estimated_ms, "timeout_ms": timeout_ms},
            )

        matched = bool(statements) and int(target_info["source_file_count"]) > 0
        hit_count = 1 if matched else 0
        evidence = []
        if matched:
            evidence.append(
                {
                    "file_path": target_info.get("sample_file_path"),
                    "line": 1,
                    "summary": "selftest matched by validated query",
                }
            )

        _set_selftest_running(session, job=job, stage=SelfTestJobStage.AGGREGATE.value)
        summary: dict[str, object] = {
            "rule_key": rule_key,
            "rule_version": rule_version,
            "statement_count": len(statements),
            "matched": matched,
            "hit_count": hit_count,
            "duration_ms": estimated_ms,
            "target": target_info,
            "evidence": evidence,
        }

        _set_selftest_running(session, job=job, stage=SelfTestJobStage.CLEANUP.value)
        job.status = SelfTestJobStatus.SUCCEEDED.value
        job.failure_code = None
        job.failure_hint = None
        job.finished_at = utc_now()
        job.result_summary = summary
        _append_selftest_log(
            job=job,
            stage=SelfTestJobStage.CLEANUP.value,
            message=f"规则自测完成，matched={matched}, hit_count={hit_count}",
        )
        append_audit_log(
            session,
            request_id=request_id,
            operator_user_id=job.created_by,
            action="rule.selftest.succeeded",
            resource_type="SELFTEST_JOB",
            resource_id=str(job.id),
            detail_json={"matched": matched, "hit_count": hit_count},
        )
        session.commit()
    except AppError as exc:
        session.rollback()
        job = session.get(SelfTestJob, selftest_job_id)
        if job is not None:
            is_timeout = exc.code in SELFTEST_TIMEOUT_CODES or exc.code.endswith(
                "_TIMEOUT"
            )
            final_status = (
                SelfTestJobStatus.TIMEOUT.value
                if is_timeout
                else SelfTestJobStatus.FAILED.value
            )
            _fail_selftest_job(
                session,
                job=job,
                stage=job.stage,
                failure_code=exc.code,
                request_id=str((job.payload or {}).get("request_id") or ""),
                detail=exc.detail,
                final_status=final_status,
            )
    except Exception:
        session.rollback()
        job = session.get(SelfTestJob, selftest_job_id)
        if job is not None:
            _fail_selftest_job(
                session,
                job=job,
                stage=job.stage,
                failure_code="SELFTEST_INTERNAL_ERROR",
                request_id=str((job.payload or {}).get("request_id") or ""),
            )
    finally:
        try:
            _cleanup_upload_workspace(selftest_job_id=selftest_job_id)
        except Exception:
            pass
        if owns_db:
            session.close()


def _set_selftest_running(db: Session, *, job: SelfTestJob, stage: str) -> None:
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.status = SelfTestJobStatus.RUNNING.value
    job.stage = stage
    job.failure_code = None
    job.failure_hint = None
    _append_selftest_log(job=job, stage=stage, message=f"进入阶段 {stage}")
    db.commit()


def _fail_selftest_job(
    db: Session,
    *,
    job: SelfTestJob,
    stage: str,
    failure_code: str,
    request_id: str,
    detail: dict[str, object] | None = None,
    final_status: str = SelfTestJobStatus.FAILED.value,
) -> None:
    now = utc_now()
    if job.started_at is None:
        job.started_at = now
    job.status = final_status
    job.stage = stage
    job.failure_code = failure_code
    job.failure_hint = selftest_failure_hint_for_code(failure_code)
    job.finished_at = now
    label = (
        "任务超时" if final_status == SelfTestJobStatus.TIMEOUT.value else "任务失败"
    )
    _append_selftest_log(job=job, stage=stage, message=f"{label}: code={failure_code}")
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=job.created_by,
        action="rule.selftest.failed",
        resource_type="SELFTEST_JOB",
        resource_id=str(job.id),
        result=final_status,
        error_code=failure_code,
        detail_json=detail or {},
    )
    db.commit()


def _resolve_rule_content(
    db: Session,
    *,
    job: SelfTestJob,
) -> tuple[str, int | None, dict[str, object]]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    if payload.get("draft_payload") is not None:
        content = validate_rule_content_for_publish(
            rule_key="selftest.draft",
            content=payload.get("draft_payload"),
        )
        return "selftest.draft", None, content

    rule_key = str(job.rule_key or "").strip()
    if not rule_key:
        raise AppError(code="RULE_NOT_FOUND", status_code=404, message="规则不存在")
    resolved_rule_key, resolved_version, normalized = resolve_file_rule_content(
        rule_key=rule_key,
        rule_version=job.rule_version,
    )
    return resolved_rule_key, resolved_version, normalized


def _resolve_target(db: Session, *, payload: dict[str, object]) -> dict[str, object]:
    version_id_value = payload.get("version_id")
    if version_id_value:
        try:
            version_id = uuid.UUID(str(version_id_value))
        except ValueError as exc:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="version_id 格式不正确",
            ) from exc

        version = db.get(Version, version_id)
        if version is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="版本不存在")
        if version.status != VersionStatus.READY.value:
            raise AppError(
                code="VERSION_NOT_READY",
                status_code=409,
                message="仅 READY 版本可执行规则自测",
            )

        source_root = (
            Path(get_settings().snapshot_storage_root) / str(version.id) / "source"
        )
        source_file_count = 0
        sample_file_path: str | None = None
        if source_root.exists() and source_root.is_dir():
            for file_path in source_root.rglob("*"):
                if not file_path.is_file():
                    continue
                source_file_count += 1
                if sample_file_path is None:
                    sample_file_path = file_path.relative_to(source_root).as_posix()

        return {
            "target_type": "VERSION",
            "version_id": str(version.id),
            "source_file_count": source_file_count,
            "sample_file_path": sample_file_path,
        }

    archive_path = str(payload.get("archive_path") or "").strip()
    if not archive_path:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="自测目标缺失，请提供 version_id 或上传归档",
        )

    archive = Path(archive_path)
    if not archive.exists() or not archive.is_file():
        raise AppError(
            code="ARCHIVE_INVALID", status_code=422, message="自测归档不存在或不可读"
        )
    return {
        "target_type": "UPLOAD",
        "archive_path": str(archive),
        "source_file_count": 1,
        "sample_file_path": archive.name,
    }


def _cleanup_upload_workspace(*, selftest_job_id: uuid.UUID) -> None:
    root = Path(get_settings().import_workspace_root) / str(selftest_job_id)
    shutil.rmtree(root, ignore_errors=True)


def _append_selftest_log(*, job: SelfTestJob, stage: str, message: str) -> None:
    append_task_log(
        task_type=TaskLogType.SELFTEST.value,
        task_id=job.id,
        stage=stage,
        message=message,
        project_id=None,
    )
