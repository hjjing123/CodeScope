from __future__ import annotations

import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    Finding,
    FindingAIAssessment,
    FindingPath,
    FindingPathStep,
    Job,
    JobStatus,
    JobStep,
    JobStepStatus,
    JobType,
    Report,
    ReportFormat,
    ReportJobStage,
    ReportStatus,
    ReportType,
    TaskLogType,
    utc_now,
)
from app.schemas.report import ReportPayload
from app.services.ai_service import (
    build_finding_ai_review_summary,
    map_latest_finding_ai_assessments,
)
from app.services.audit_service import append_audit_log
from app.services.finding_presentation_service import build_finding_presentation
from app.services.report_storage_service import (
    build_generated_report_object_key,
    build_report_bundle_object_key,
    build_report_manifest_object_key,
    reset_report_job_root,
    resolve_report_object_path,
    write_report_bytes,
    write_report_text,
)
from app.services.snapshot_storage_service import read_snapshot_file_context
from app.services.task_log_service import append_task_log


REPORT_GENERATION_MODE_JOB_ALL = "JOB_ALL"
REPORT_GENERATION_MODE_FINDING_SET = "FINDING_SET"

TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TIMEOUT.value,
    }
)
TERMINAL_STEP_STATUSES = frozenset(
    {
        JobStepStatus.SUCCEEDED.value,
        JobStepStatus.FAILED.value,
        JobStepStatus.CANCELED.value,
    }
)
REPORT_STEP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("prepare", "Prepare"),
    ("render", "Render"),
    ("package", "Package"),
    ("cleanup", "Cleanup"),
)
REPORT_FAILURE_HINTS: dict[str, str] = {
    "REPORT_DISPATCH_FAILED": "报告任务派发失败，请检查调度器或 Worker 状态。",
    "REPORT_SCAN_JOB_NOT_TERMINAL": "仅已结束的扫描任务可生成报告。",
    "REPORT_NO_FINDINGS": "来源扫描任务下没有可生成报告的漏洞。",
    "REPORT_ALL_GENERATIONS_FAILED": "所有目标漏洞报告均生成失败，请查看任务日志定位原因。",
    "REPORT_JOB_FAILED": "报告任务执行失败，请查看任务日志定位原因。",
}


@dataclass(frozen=True, slots=True)
class PreparedReportSelection:
    scan_job: Job
    findings: list[Finding]
    generation_mode: str
    bundle_expected: bool

    @property
    def requested_count(self) -> int:
        return len(self.findings)

    @property
    def finding_ids(self) -> list[uuid.UUID]:
        return [item.id for item in self.findings]


def _normalize_report_options(raw: object) -> dict[str, object]:
    payload = raw if isinstance(raw, dict) else {}
    format_value = (
        str(payload.get("format") or ReportFormat.MARKDOWN.value).strip().upper()
    )
    if format_value != ReportFormat.MARKDOWN.value:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="当前仅支持 MARKDOWN 格式的漏洞报告",
        )
    return {
        "format": format_value,
        "include_code_snippets": bool(payload.get("include_code_snippets", True)),
        "include_ai_sections": bool(payload.get("include_ai_sections", True)),
    }


def initialize_report_job_steps(db: Session, *, job_id: uuid.UUID) -> list[JobStep]:
    existing = db.scalars(select(JobStep).where(JobStep.job_id == job_id)).all()
    existing_keys = {item.step_key for item in existing}
    created: list[JobStep] = []
    for index, (step_key, display_name) in enumerate(REPORT_STEP_DEFINITIONS, start=1):
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


def create_report_job(
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
        job_type=JobType.REPORT.value,
        payload=payload,
        status=JobStatus.PENDING.value,
        stage=ReportJobStage.PREPARE.value,
        created_by=created_by,
        result_summary={},
    )
    db.add(job)
    db.flush()
    initialize_report_job_steps(db, job_id=job.id)
    return job


def prepare_report_selection(
    db: Session,
    *,
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    job_id: uuid.UUID,
    generation_mode: str,
    finding_ids: list[uuid.UUID],
) -> PreparedReportSelection:
    normalized_mode = str(generation_mode or "").strip().upper()
    if normalized_mode not in {
        REPORT_GENERATION_MODE_JOB_ALL,
        REPORT_GENERATION_MODE_FINDING_SET,
    }:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="generation_mode 值不合法",
            detail={
                "allowed_generation_modes": [
                    REPORT_GENERATION_MODE_FINDING_SET,
                    REPORT_GENERATION_MODE_JOB_ALL,
                ]
            },
        )

    scan_job = db.get(Job, job_id)
    if scan_job is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="来源扫描任务不存在")
    if scan_job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="仅支持基于扫描任务生成漏洞报告",
        )
    if scan_job.project_id != project_id:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="job_id 不属于当前项目",
        )
    if scan_job.version_id != version_id:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="job_id 不属于当前代码快照",
        )
    if scan_job.status not in TERMINAL_JOB_STATUSES:
        raise AppError(
            code="REPORT_SCAN_JOB_NOT_TERMINAL",
            status_code=409,
            message="仅已结束的扫描任务可生成报告",
        )

    if normalized_mode == REPORT_GENERATION_MODE_JOB_ALL:
        findings = db.scalars(
            select(Finding)
            .where(Finding.job_id == scan_job.id)
            .order_by(Finding.created_at.asc())
        ).all()
    else:
        target_ids = _dedupe_uuid_list(finding_ids)
        if not target_ids:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="FINDING_SET 模式必须提供至少一个 finding_id",
            )
        rows = db.scalars(select(Finding).where(Finding.id.in_(target_ids))).all()
        finding_map = {item.id: item for item in rows}
        findings = []
        for finding_id in target_ids:
            finding = finding_map.get(finding_id)
            if finding is None:
                raise AppError(
                    code="NOT_FOUND", status_code=404, message="指定漏洞不存在"
                )
            if finding.job_id != scan_job.id:
                raise AppError(
                    code="INVALID_ARGUMENT",
                    status_code=422,
                    message="指定漏洞不属于当前扫描任务",
                )
            findings.append(finding)

    if not findings:
        raise AppError(
            code="REPORT_NO_FINDINGS",
            status_code=409,
            message="当前扫描任务下没有可生成报告的漏洞",
        )

    bundle_expected = (
        normalized_mode == REPORT_GENERATION_MODE_JOB_ALL or len(findings) > 1
    )
    return PreparedReportSelection(
        scan_job=scan_job,
        findings=findings,
        generation_mode=normalized_mode,
        bundle_expected=bundle_expected,
    )


def dispatch_report_job(db: Session, *, job: Job) -> dict[str, object]:
    settings = get_settings()
    backend = (settings.report_dispatch_backend or "sync").strip().lower()
    allow_fallback = bool(settings.report_dispatch_fallback_to_sync)

    if backend == "celery":
        try:
            from app.worker.tasks import enqueue_report_job

            bind = db.get_bind()
            bind_engine = getattr(bind, "engine", bind)
            task_id = enqueue_report_job(report_job_id=job.id, db_bind=bind_engine)
            if task_id:
                dispatch_info = {
                    "backend": "celery_or_local",
                    "task_id": task_id,
                    "requested_backend": "celery",
                }
                job.payload = {**(job.payload or {}), "dispatch": dispatch_info}
                _append_report_log(
                    report_job_id=job.id,
                    stage=ReportJobStage.PREPARE.value,
                    message=f"report job queued, task_id={task_id}",
                    project_id=job.project_id,
                    db=db,
                )
                db.flush()
                return dispatch_info
            if not allow_fallback:
                raise AppError(
                    code="REPORT_DISPATCH_FAILED",
                    status_code=503,
                    message="报告任务派发失败",
                )
        except Exception as exc:
            if not allow_fallback:
                raise AppError(
                    code="REPORT_DISPATCH_FAILED",
                    status_code=503,
                    message="报告任务派发失败",
                    detail={"reason": str(exc)},
                ) from exc
            dispatch_info = {
                "backend": "sync",
                "task_id": None,
                "requested_backend": "celery",
                "fallback_reason": str(exc),
            }
            job.payload = {**(job.payload or {}), "dispatch": dispatch_info}
            _append_report_log(
                report_job_id=job.id,
                stage=ReportJobStage.PREPARE.value,
                message=f"dispatch fallback to sync, reason={exc}",
                project_id=job.project_id,
                db=db,
            )
            db.flush()
            run_report_job(job_id=job.id, db=db)
            return dispatch_info

    dispatch_info = {"backend": "sync", "task_id": None, "requested_backend": backend}
    job.payload = {**(job.payload or {}), "dispatch": dispatch_info}
    _append_report_log(
        report_job_id=job.id,
        stage=ReportJobStage.PREPARE.value,
        message="report job running in sync mode",
        project_id=job.project_id,
        db=db,
    )
    db.flush()
    run_report_job(job_id=job.id, db=db)
    return dispatch_info


def mark_report_dispatch_failed(
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
    job.stage = ReportJobStage.PREPARE.value
    job.failure_code = "REPORT_DISPATCH_FAILED"
    job.failure_stage = ReportJobStage.PREPARE.value
    job.failure_category = "SYSTEM"
    job.failure_hint = REPORT_FAILURE_HINTS["REPORT_DISPATCH_FAILED"]
    job.finished_at = utc_now()
    if job.started_at is None:
        job.started_at = job.finished_at
    _append_report_log(
        report_job_id=job.id,
        stage=ReportJobStage.PREPARE.value,
        message="report dispatch failed: code=REPORT_DISPATCH_FAILED",
        project_id=job.project_id,
        db=db,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="report.dispatch.failed",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        result="FAILED",
        error_code="REPORT_DISPATCH_FAILED",
    )
    db.commit()


def run_report_job(*, job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    job: Job | None = None
    request_id = ""

    try:
        job = session.get(Job, job_id)
        if job is None or job.job_type != JobType.REPORT.value:
            return
        if job.status in TERMINAL_JOB_STATUSES:
            return

        payload = job.payload if isinstance(job.payload, dict) else {}
        request_id = str(payload.get("request_id") or "")
        options = _normalize_report_options(payload.get("options"))
        selection = prepare_report_selection(
            session,
            project_id=job.project_id,
            version_id=job.version_id,
            job_id=_coerce_required_uuid(
                payload.get("scan_job_id"), field_name="scan_job_id"
            ),
            generation_mode=str(payload.get("generation_mode") or ""),
            finding_ids=_coerce_uuid_list(payload.get("finding_ids")),
        )
        generated_report_ids: list[str] = []
        generated_items: list[dict[str, object]] = []
        failed_items: list[dict[str, object]] = []

        reset_report_job_root(report_job_id=job.id)
        _set_report_job_running(session, job=job, stage=ReportJobStage.PREPARE.value)
        job.result_summary = {
            "report_type": ReportType.FINDING.value,
            "generation_mode": selection.generation_mode,
            "scan_job_id": str(selection.scan_job.id),
            "requested_count": selection.requested_count,
            "processed_count": 0,
            "generated_count": 0,
            "failed_count": 0,
            "partial": False,
            "bundle_expected": selection.bundle_expected,
        }
        _append_report_log(
            report_job_id=job.id,
            stage=ReportJobStage.PREPARE.value,
            message=(
                f"prepare report job, generation_mode={selection.generation_mode}, "
                f"requested_count={selection.requested_count}, scan_job_id={selection.scan_job.id}"
            ),
            project_id=job.project_id,
            db=session,
        )
        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="prepare",
            status=JobStepStatus.SUCCEEDED.value,
        )

        _set_report_job_running(session, job=job, stage=ReportJobStage.RENDER.value)
        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="render",
            status=JobStepStatus.RUNNING.value,
        )

        ai_by_finding = (
            map_latest_finding_ai_assessments(
                session, finding_ids=[item.id for item in selection.findings]
            )
            if bool(options.get("include_ai_sections")) and selection.findings
            else {}
        )

        for index, finding in enumerate(selection.findings, start=1):
            report: Report | None = None
            object_key: str | None = None
            try:
                presentation = build_finding_presentation(
                    version_id=finding.version_id,
                    rule_key=finding.rule_key,
                    vuln_type=finding.vuln_type,
                    source_file=finding.source_file,
                    source_line=finding.source_line,
                    file_path=finding.file_path,
                    line_start=finding.line_start,
                )
                report = Report(
                    project_id=finding.project_id,
                    version_id=finding.version_id,
                    job_id=selection.scan_job.id,
                    report_job_id=job.id,
                    finding_id=finding.id,
                    report_type=ReportType.FINDING.value,
                    status=ReportStatus.DRAFT.value,
                    format=str(options["format"]),
                    created_by=job.created_by,
                )
                session.add(report)
                session.flush()

                file_name = _build_report_filename(
                    index=index,
                    finding=finding,
                    vuln_display_name=presentation.get("vuln_display_name"),
                )
                object_key = build_generated_report_object_key(
                    report_job_id=job.id,
                    filename=file_name,
                )
                content = _render_finding_report_markdown(
                    session,
                    report_id=report.id,
                    finding=finding,
                    scan_job=selection.scan_job,
                    options=options,
                    ai_assessment=ai_by_finding.get(finding.id),
                    generated_at=utc_now(),
                )
                write_report_text(object_key=object_key, content=content)
                report.object_key = object_key
                session.flush()

                generated_report_ids.append(str(report.id))
                generated_items.append(
                    {
                        "report_id": str(report.id),
                        "finding_id": str(finding.id),
                        "file_name": file_name,
                        "object_key": object_key,
                        "severity": finding.severity,
                        "status": "SUCCEEDED",
                    }
                )
                _append_report_log(
                    report_job_id=job.id,
                    stage=ReportJobStage.RENDER.value,
                    message=(
                        f"[render] generated finding_id={finding.id}, progress={index}/"
                        f"{selection.requested_count}"
                    ),
                    project_id=job.project_id,
                    db=session,
                )
            except AppError as exc:
                _cleanup_failed_report_attempt(
                    session, report=report, object_key=object_key
                )
                failed_items.append(
                    {
                        "finding_id": str(finding.id),
                        "status": "FAILED",
                        "error_code": exc.code,
                        "message": exc.message,
                    }
                )
                _append_report_log(
                    report_job_id=job.id,
                    stage=ReportJobStage.RENDER.value,
                    message=(
                        f"[render] failed finding_id={finding.id}, code={exc.code}, progress={index}/"
                        f"{selection.requested_count}"
                    ),
                    project_id=job.project_id,
                    db=session,
                )
            except Exception as exc:
                _cleanup_failed_report_attempt(
                    session, report=report, object_key=object_key
                )
                failed_items.append(
                    {
                        "finding_id": str(finding.id),
                        "status": "FAILED",
                        "error_code": "REPORT_RENDER_FAILED",
                        "message": _truncate_text(
                            str(exc) or exc.__class__.__name__, 512
                        ),
                    }
                )
                _append_report_log(
                    report_job_id=job.id,
                    stage=ReportJobStage.RENDER.value,
                    message=(
                        f"[render] failed finding_id={finding.id}, code=REPORT_RENDER_FAILED, progress="
                        f"{index}/{selection.requested_count}"
                    ),
                    project_id=job.project_id,
                    db=session,
                )

            job.result_summary = {
                **(job.result_summary or {}),
                "processed_count": index,
                "generated_count": len(generated_items),
                "failed_count": len(failed_items),
            }
            session.flush()

        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="render",
            status=(
                JobStepStatus.SUCCEEDED.value
                if generated_items
                else JobStepStatus.FAILED.value
            ),
        )

        _set_report_job_running(session, job=job, stage=ReportJobStage.PACKAGE.value)
        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="package",
            status=JobStepStatus.RUNNING.value,
        )

        partial = bool(generated_items) and bool(failed_items)
        manifest_payload = {
            "report_job_id": str(job.id),
            "report_type": ReportType.FINDING.value,
            "generation_mode": selection.generation_mode,
            "scan_job_id": str(selection.scan_job.id),
            "scan_job_status": selection.scan_job.status,
            "requested_count": selection.requested_count,
            "generated_count": len(generated_items),
            "failed_count": len(failed_items),
            "partial": partial,
            "items": generated_items,
            "failures": failed_items,
        }
        manifest_text = json.dumps(manifest_payload, ensure_ascii=False, indent=2)
        manifest_object_key = build_report_manifest_object_key(report_job_id=job.id)
        write_report_text(object_key=manifest_object_key, content=manifest_text)

        bundle_object_key: str | None = None
        bundle_filename: str | None = None
        if selection.bundle_expected and generated_items:
            bundle_filename = _build_bundle_filename(
                generation_mode=selection.generation_mode,
                scan_job_id=selection.scan_job.id,
            )
            bundle_object_key = build_report_bundle_object_key(
                report_job_id=job.id,
                filename=bundle_filename,
            )
            _write_report_bundle(
                bundle_object_key=bundle_object_key,
                manifest_content=manifest_text.encode("utf-8"),
                generated_items=generated_items,
            )

        _append_report_log(
            report_job_id=job.id,
            stage=ReportJobStage.PACKAGE.value,
            message=(
                f"[package] manifest_written=true, bundle_created={bool(bundle_object_key)}, "
                f"generated_count={len(generated_items)}, failed_count={len(failed_items)}"
            ),
            project_id=job.project_id,
            db=session,
        )
        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="package",
            status=JobStepStatus.SUCCEEDED.value,
        )

        _set_report_job_running(session, job=job, stage=ReportJobStage.CLEANUP.value)
        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="cleanup",
            status=JobStepStatus.RUNNING.value,
        )
        job.result_summary = {
            **(job.result_summary or {}),
            "generated_count": len(generated_items),
            "failed_count": len(failed_items),
            "partial": partial,
            "report_ids": generated_report_ids,
            "manifest_object_key": manifest_object_key,
            "bundle_object_key": bundle_object_key,
            "bundle_filename": bundle_filename,
        }
        job.finished_at = utc_now()
        if generated_items:
            job.status = JobStatus.SUCCEEDED.value
            job.failure_code = None
            job.failure_stage = None
            job.failure_category = None
            job.failure_hint = None
        else:
            job.status = JobStatus.FAILED.value
            job.failure_code = "REPORT_ALL_GENERATIONS_FAILED"
            job.failure_stage = ReportJobStage.RENDER.value
            job.failure_category = "SYSTEM"
            job.failure_hint = REPORT_FAILURE_HINTS["REPORT_ALL_GENERATIONS_FAILED"]
        _append_report_log(
            report_job_id=job.id,
            stage=ReportJobStage.CLEANUP.value,
            message=(
                f"[cleanup] report job completed, generated_count={len(generated_items)}, "
                f"failed_count={len(failed_items)}, partial={partial}"
            ),
            project_id=job.project_id,
            db=session,
        )
        _set_report_step_status(
            session,
            job_id=job.id,
            step_key="cleanup",
            status=JobStepStatus.SUCCEEDED.value,
        )
        append_audit_log(
            session,
            request_id=request_id,
            operator_user_id=job.created_by,
            action="report.generated" if generated_items else "report.failed",
            resource_type="JOB",
            resource_id=str(job.id),
            project_id=job.project_id,
            result=job.status,
            error_code=job.failure_code,
            detail_json={
                "generation_mode": selection.generation_mode,
                "scan_job_id": str(selection.scan_job.id),
                "requested_count": selection.requested_count,
                "generated_count": len(generated_items),
                "failed_count": len(failed_items),
                "partial": partial,
            },
        )
        session.commit()
    except AppError as exc:
        if session.is_active:
            session.rollback()
        if job is not None:
            _fail_report_job(
                session,
                job_id=job.id,
                request_id=request_id,
                failure_code=exc.code,
                failure_stage=job.stage,
                message=exc.message,
            )
    except Exception as exc:
        if session.is_active:
            session.rollback()
        if job is not None:
            _fail_report_job(
                session,
                job_id=job.id,
                request_id=request_id,
                failure_code="REPORT_JOB_FAILED",
                failure_stage=job.stage,
                message=_truncate_text(str(exc) or exc.__class__.__name__, 512),
            )
    finally:
        if owns_db:
            session.close()


def build_report_payload(
    report: Report, *, finding: Finding | None = None
) -> ReportPayload:
    vuln_display_name: str | None = None
    entry_display: str | None = None
    entry_kind: str | None = None
    rule_key: str | None = None
    vuln_type: str | None = None
    severity: str | None = None
    finding_status: str | None = None

    if finding is not None:
        presentation = build_finding_presentation(
            version_id=finding.version_id,
            rule_key=finding.rule_key,
            vuln_type=finding.vuln_type,
            source_file=finding.source_file,
            source_line=finding.source_line,
            file_path=finding.file_path,
            line_start=finding.line_start,
        )
        vuln_display_name = presentation.get("vuln_display_name")
        entry_display = presentation.get("entry_display")
        entry_kind = presentation.get("entry_kind")
        rule_key = finding.rule_key
        vuln_type = finding.vuln_type
        severity = finding.severity
        finding_status = finding.status

    file_name = None
    if report.object_key:
        file_name = PurePosixPath(str(report.object_key)).name or None

    return ReportPayload(
        id=report.id,
        project_id=report.project_id,
        version_id=report.version_id,
        job_id=report.job_id,
        report_job_id=report.report_job_id,
        finding_id=report.finding_id,
        report_type=report.report_type,
        status=report.status,
        format=getattr(report, "format", ReportFormat.MARKDOWN.value),
        object_key=report.object_key,
        file_name=file_name,
        created_by=getattr(report, "created_by", None),
        created_at=report.created_at,
        rule_key=rule_key,
        vuln_type=vuln_type,
        vuln_display_name=vuln_display_name,
        severity=severity,
        finding_status=finding_status,
        entry_display=entry_display,
        entry_kind=entry_kind,
    )


def _append_report_log(
    *,
    report_job_id: uuid.UUID,
    stage: str,
    message: str,
    project_id: uuid.UUID,
    db: Session | None,
) -> None:
    append_task_log(
        task_type=TaskLogType.REPORT.value,
        task_id=report_job_id,
        stage=stage,
        message=message,
        project_id=project_id,
        db=db,
    )


def _set_report_job_running(db: Session, *, job: Job, stage: str) -> None:
    if job.started_at is None:
        job.started_at = utc_now()
    job.status = JobStatus.RUNNING.value
    job.stage = stage
    db.flush()


def _set_report_step_status(
    db: Session,
    *,
    job_id: uuid.UUID,
    step_key: str,
    status: str,
) -> JobStep:
    step = db.scalar(
        select(JobStep).where(JobStep.job_id == job_id, JobStep.step_key == step_key)
    )
    if step is None:
        raise AppError(
            code="NOT_FOUND",
            status_code=404,
            message="步骤不存在",
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
        step.duration_ms = max(
            0,
            int(
                (
                    _coerce_utc_datetime(step.finished_at)
                    - _coerce_utc_datetime(step.started_at)
                ).total_seconds()
                * 1000
            ),
        )
    db.flush()
    return step


def _coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)


def _fail_report_job(
    db: Session,
    *,
    job_id: uuid.UUID,
    request_id: str,
    failure_code: str,
    failure_stage: str | None,
    message: str,
) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    stage = str(failure_stage or job.stage or ReportJobStage.PREPARE.value)
    job.status = JobStatus.FAILED.value
    job.stage = stage
    job.failure_code = failure_code
    job.failure_stage = stage
    job.failure_category = _report_failure_category(failure_code)
    job.failure_hint = REPORT_FAILURE_HINTS.get(
        failure_code, message or REPORT_FAILURE_HINTS["REPORT_JOB_FAILED"]
    )
    job.finished_at = utc_now()
    if job.started_at is None:
        job.started_at = job.finished_at
    _append_report_log(
        report_job_id=job.id,
        stage=stage,
        message=f"report job failed, code={failure_code}, message={_truncate_text(message, 300)}",
        project_id=job.project_id,
        db=db,
    )
    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=job.created_by,
        action="report.failed",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        result="FAILED",
        error_code=failure_code,
        detail_json={"message": _truncate_text(message, 300)},
    )
    db.commit()


def _report_failure_category(failure_code: str) -> str:
    if failure_code in {
        "INVALID_ARGUMENT",
        "NOT_FOUND",
        "REPORT_SCAN_JOB_NOT_TERMINAL",
    }:
        return "INPUT"
    if failure_code in {
        "OBJECT_NOT_FOUND",
        "PATH_NOT_FOUND",
        "FILE_BINARY_NOT_SUPPORTED",
    }:
        return "STORAGE"
    return "SYSTEM"


def _coerce_required_uuid(value: object, *, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message=f"{field_name} 格式不正确",
        ) from exc


def _coerce_uuid_list(value: object) -> list[uuid.UUID]:
    if not isinstance(value, list):
        return []
    result: list[uuid.UUID] = []
    for item in value:
        try:
            result.append(uuid.UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return result


def _dedupe_uuid_list(values: list[uuid.UUID]) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    result: list[uuid.UUID] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _build_report_filename(
    *, index: int, finding: Finding, vuln_display_name: str | None
) -> str:
    slug = _slugify(
        vuln_display_name or finding.vuln_type or finding.rule_key or "finding"
    )
    short_id = str(finding.id).split("-", 1)[0]
    return f"{index:04d}_{finding.severity.lower()}_{slug}_{short_id}.md"


def _build_bundle_filename(*, generation_mode: str, scan_job_id: uuid.UUID) -> str:
    suffix = (
        "all_findings"
        if generation_mode == REPORT_GENERATION_MODE_JOB_ALL
        else "selected_findings"
    )
    return f"finding_reports_{suffix}_{scan_job_id}.zip"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip().lower()).strip(
        "_"
    )
    return normalized[:32] or "finding"


def _truncate_text(value: str, limit: int) -> str:
    normalized = str(value or "")
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)] + "..."


def _cleanup_failed_report_attempt(
    db: Session,
    *,
    report: Report | None,
    object_key: str | None,
) -> None:
    if report is not None:
        try:
            db.delete(report)
            db.flush()
        except Exception:
            pass
    if object_key is None:
        return
    try:
        path = resolve_report_object_path(object_key=object_key)
    except AppError:
        return
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        return


def _render_finding_report_markdown(
    db: Session,
    *,
    report_id: uuid.UUID,
    finding: Finding,
    scan_job: Job,
    options: dict[str, object],
    ai_assessment: FindingAIAssessment | None,
    generated_at: datetime,
) -> str:
    presentation = build_finding_presentation(
        version_id=finding.version_id,
        rule_key=finding.rule_key,
        vuln_type=finding.vuln_type,
        source_file=finding.source_file,
        source_line=finding.source_line,
        file_path=finding.file_path,
        line_start=finding.line_start,
    )
    lines: list[str] = [
        "# Finding Report",
        "",
        "## Metadata",
        "",
        f"- Report ID: `{report_id}`",
        f"- Generated At: `{generated_at.isoformat()}`",
        f"- Source Scan Job: `{scan_job.id}`",
        f"- Source Scan Status: `{scan_job.status}`",
        f"- Project ID: `{finding.project_id}`",
        f"- Version ID: `{finding.version_id}`",
        f"- Finding ID: `{finding.id}`",
        f"- Rule Key: `{finding.rule_key}`",
        f"- Vulnerability: `{presentation.get('vuln_display_name') or '-'}`",
        f"- Severity: `{finding.severity}`",
        f"- Finding Status: `{finding.status}`",
        f"- Entry: `{presentation.get('entry_display') or '-'}`",
        f"- Primary Location: `{_format_location(finding.file_path, finding.line_start)}`",
        f"- Source Location: `{_format_location(finding.source_file, finding.source_line)}`",
        f"- Sink Location: `{_format_location(finding.sink_file, finding.sink_line)}`",
        f"- Path Recorded: `{bool(finding.has_path)}`",
        f"- Path Length: `{finding.path_length if finding.path_length is not None else '-'}`",
        "",
    ]
    if scan_job.status != JobStatus.SUCCEEDED.value:
        lines.extend(
            [
                "> Note: the source scan did not finish with status `SUCCEEDED`; findings may be partial.",
                "",
            ]
        )

    lines.extend(
        [
            "## Evidence",
            "",
            _render_json_code_block(finding.evidence_json, language="json"),
            "",
        ]
    )

    path_lines = _load_persisted_path_lines(db, finding_id=finding.id)
    lines.extend(["## Path Overview", ""])
    if path_lines:
        for item in path_lines:
            lines.append(f"- {item}")
    else:
        lines.append("- No persisted path steps available.")
    lines.append("")

    if bool(options.get("include_code_snippets")):
        lines.extend(["## Code Snippets", ""])
        snippets = _load_report_snippets(finding=finding)
        if snippets:
            for snippet in snippets:
                lines.extend(
                    [
                        f"### {snippet['label']}",
                        "",
                        f"- File: `{snippet['file_path']}`",
                        f"- Range: `{snippet['start_line']}-{snippet['end_line']}`",
                        "",
                        f"```{snippet['language']}",
                        snippet["content"],
                        "```",
                        "",
                    ]
                )
        else:
            lines.extend(["- Code snippets are not available.", ""])

    if bool(options.get("include_ai_sections")):
        lines.extend(["## AI Review", ""])
        if ai_assessment is None:
            lines.extend(["- No AI assessment available.", ""])
        else:
            ai_summary = build_finding_ai_review_summary(ai_assessment)
            lines.extend(
                [
                    f"- Assessment Status: `{ai_summary.get('status') or '-'}`",
                    f"- Verdict: `{ai_summary.get('verdict') or '-'}`",
                    f"- Confidence: `{ai_summary.get('confidence') or '-'}`",
                    f"- Updated At: `{ai_summary.get('updated_at') or '-'}`",
                    "",
                    "### AI Summary JSON",
                    "",
                    _render_json_code_block(
                        ai_assessment.summary_json, language="json"
                    ),
                    "",
                ]
            )
            response_text = str(ai_assessment.response_text or "").strip()
            if response_text:
                lines.extend(
                    [
                        "### AI Response Text",
                        "",
                        "```text",
                        _truncate_text(response_text, 8000),
                        "```",
                        "",
                    ]
                )

    return "\n".join(lines).strip() + "\n"


def _render_json_code_block(payload: object, *, language: str) -> str:
    try:
        rendered = json.dumps(
            payload if payload is not None else {}, ensure_ascii=False, indent=2
        )
    except TypeError:
        rendered = json.dumps({}, ensure_ascii=False, indent=2)
    return "\n".join([f"```{language}", _truncate_text(rendered, 8000), "```"])


def _load_persisted_path_lines(db: Session, *, finding_id: uuid.UUID) -> list[str]:
    path_row = db.scalar(
        select(FindingPath)
        .where(FindingPath.finding_id == finding_id)
        .order_by(FindingPath.path_order.asc(), FindingPath.path_length.asc())
        .limit(1)
    )
    if path_row is None:
        return []
    steps = db.scalars(
        select(FindingPathStep)
        .where(FindingPathStep.finding_path_id == path_row.id)
        .order_by(FindingPathStep.step_order.asc())
        .limit(12)
    ).all()
    lines: list[str] = []
    for index, step in enumerate(steps, start=1):
        display_name = (
            step.display_name
            or step.symbol_name
            or step.func_name
            or _format_location(step.file_path, step.line_no)
        )
        lines.append(
            f"{index}. {display_name} @ {_format_location(step.file_path, step.line_no)}"
        )
    return lines


def _load_report_snippets(*, finding: Finding) -> list[dict[str, object]]:
    snippets: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    locations = [
        ("Primary Location", finding.file_path, finding.line_start),
        ("Source", finding.source_file, finding.source_line),
        ("Sink", finding.sink_file, finding.sink_line),
    ]
    for label, file_path, line in locations:
        normalized_path = str(file_path or "").strip()
        if not normalized_path or line is None or line <= 0:
            continue
        marker = (normalized_path, int(line))
        if marker in seen:
            continue
        seen.add(marker)
        try:
            content_lines, start_line, end_line = read_snapshot_file_context(
                version_id=finding.version_id,
                path=normalized_path,
                line=int(line),
                before=3,
                after=3,
            )
        except AppError:
            continue
        snippets.append(
            {
                "label": label,
                "file_path": normalized_path,
                "start_line": start_line,
                "end_line": end_line,
                "content": "\n".join(content_lines),
                "language": _language_from_path(normalized_path),
            }
        )
    return snippets


def _language_from_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    mapping = {
        ".java": "java",
        ".kt": "kotlin",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".json": "json",
        ".xml": "xml",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".properties": "properties",
    }
    return mapping.get(suffix, "text")


def _format_location(file_path: str | None, line: int | None) -> str:
    normalized_path = str(file_path or "").strip() or "-"
    if line is None:
        return normalized_path
    return f"{normalized_path}:{line}"


def _write_report_bundle(
    *,
    bundle_object_key: str,
    manifest_content: bytes,
    generated_items: list[dict[str, object]],
) -> None:
    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_content)
        for item in generated_items:
            object_key = str(item.get("object_key") or "").strip()
            file_name = str(item.get("file_name") or "").strip()
            if not object_key or not file_name:
                continue
            path = resolve_report_object_path(object_key=object_key)
            zf.write(path, arcname=f"generated/{file_name}")
    write_report_bytes(object_key=bundle_object_key, content=buffer.getvalue())


def get_report_download_path(*, report: Report) -> tuple[str, Path]:
    object_key = str(report.object_key or "").strip()
    if not object_key:
        raise AppError(
            code="OBJECT_NOT_FOUND", status_code=404, message="报告文件不存在"
        )
    path = resolve_report_object_path(object_key=object_key)
    if not path.exists() or not path.is_file():
        raise AppError(
            code="OBJECT_NOT_FOUND", status_code=404, message="报告文件不存在"
        )
    file_name = PurePosixPath(object_key).name or f"report_{report.id}.md"
    return str(file_name), path
