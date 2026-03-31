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
    delete_report_job_root,
    delete_report_object,
    build_generated_report_object_key,
    build_report_manifest_object_key,
    reset_report_job_root,
    resolve_report_object_path,
    write_report_bytes,
    write_report_text,
)
from app.services.snapshot_storage_service import read_snapshot_file_context
from app.services.task_log_service import append_task_log, delete_task_logs


REPORT_GENERATION_MODE_JOB_ALL = "JOB_ALL"
REPORT_GENERATION_MODE_FINDING_SET = "FINDING_SET"
REPORT_TEMPLATE_SCAN_V1 = "standard_scan_v1"
REPORT_TEMPLATE_FINDING_V1 = "standard_finding_v1"

SEVERITY_PRIORITY: dict[str, int] = {
    "HIGH": 3,
    "MED": 2,
    "LOW": 1,
}
SEVERITY_LABELS: dict[str, str] = {
    "HIGH": "高危",
    "MED": "中危",
    "LOW": "低危",
}
VULNERABILITY_IMPACT_HINTS: dict[str, str] = {
    "SQLI": "可能导致数据库数据被越权读取、篡改，严重时可进一步控制业务逻辑。",
    "XSS": "可能导致页面注入恶意脚本，影响用户会话、页面内容和敏感信息安全。",
    "SSRF": "可能导致服务端向内部网络或敏感系统发起请求，形成横向探测与访问。",
    "XXE": "可能导致服务端读取本地文件、探测内网资源或触发拒绝服务。",
    "RCE": "可能导致攻击者在服务端执行任意命令，直接影响主机安全。",
    "CMDI": "可能导致系统命令被拼接执行，扩大为主机层面风险。",
    "CODEI": "可能导致动态代码被恶意输入控制，从而执行非预期逻辑。",
    "UPLOAD": "可能导致恶意文件落地，进一步引发 webshell、覆盖文件或供应链风险。",
    "PATH_TRAVERSAL": "可能导致越界访问服务端文件，泄露配置、密钥或业务数据。",
    "OPEN_REDIRECT": "可能被用于钓鱼跳转、绕过信任边界或辅助其他攻击链。",
    "DESERIALIZATION": "可能导致对象注入、远程代码执行或高权限逻辑被滥用。",
    "SSTI": "可能让攻击者操纵模板执行流程，进一步读取信息或执行恶意表达式。",
    "JNDII": "可能触发远程加载与执行，影响应用与中间件安全。",
    "LDAPI": "可能导致目录服务查询被篡改，影响认证与权限边界。",
    "HPE": "可能导致用户访问本不属于其权限范围的数据或功能。",
    "CORS": "可能导致浏览器跨域信任范围过宽，增加敏感接口被滥用的风险。",
    "MISCONFIG": "说明系统安全配置存在缺口，可能放大其他漏洞影响。",
    "INFOLEAK": "可能泄露敏感配置、接口实现或业务数据，为后续攻击提供线索。",
    "HARDCODE_SECRET": "说明代码中存在敏感凭据硬编码，增加泄露与长期滥用风险。",
    "WEAK_PASSWORD": "说明认证口令强度不足，存在被猜解或撞库利用的风险。",
    "WEAK_HASH": "说明使用了安全性较弱的摘要算法，可能影响密码或数据保护强度。",
    "COOKIE_FLAGS": "说明 Cookie 安全属性配置不完整，可能增加会话被窃取的风险。",
}
VULNERABILITY_REMEDIATION_HINTS: dict[str, list[str]] = {
    "SQLI": [
        "将动态拼接 SQL 改为参数化查询或 ORM 绑定参数。",
        "对排序、字段名等无法参数化的输入使用白名单校验。",
    ],
    "XSS": [
        "对输出到页面的内容执行上下文相关编码。",
        "避免直接信任富文本或拼接脚本片段。",
    ],
    "SSRF": [
        "限制服务端可访问的协议、域名和地址段。",
        "对外部 URL 输入做白名单或网段校验，并关闭不必要跳转。",
    ],
    "UPLOAD": [
        "限制允许上传的文件类型、大小和扩展名，并进行内容校验。",
        "将上传文件落到隔离目录，避免直接可执行或可访问。",
    ],
    "PATH_TRAVERSAL": [
        "对文件路径做规范化与目录边界校验。",
        "避免将用户输入直接参与文件系统读写路径拼接。",
    ],
    "HARDCODE_SECRET": [
        "将敏感凭据迁移到密钥管理或环境变量。",
        "同步轮换已暴露凭据，并排查历史提交与日志残留。",
    ],
}

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
    report_type: str
    scan_job: Job
    findings: list[Finding]
    finding: Finding | None
    template_key: str

    @property
    def generated_report_count(self) -> int:
        return 1

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def target_finding_id(self) -> uuid.UUID | None:
        return self.finding.id if self.finding is not None else None


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
    report_type: str,
    finding_id: uuid.UUID | None,
) -> PreparedReportSelection:
    normalized_report_type = str(report_type or "").strip().upper()
    if normalized_report_type not in {
        ReportType.SCAN.value,
        ReportType.FINDING.value,
    }:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="report_type 值不合法",
            detail={
                "allowed_report_types": [
                    ReportType.FINDING.value,
                    ReportType.SCAN.value,
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

    findings = db.scalars(
        select(Finding)
        .where(Finding.job_id == scan_job.id)
        .order_by(Finding.created_at.asc())
    ).all()
    target_finding: Finding | None = None
    template_key = REPORT_TEMPLATE_SCAN_V1

    if normalized_report_type == ReportType.FINDING.value:
        if finding_id is None:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="FINDING 报告必须提供 finding_id",
            )
        target_finding = db.get(Finding, finding_id)
        if target_finding is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="指定漏洞不存在")
        if target_finding.job_id != scan_job.id:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="指定漏洞不属于当前扫描任务",
            )
        findings = [target_finding]
        template_key = REPORT_TEMPLATE_FINDING_V1
    elif finding_id is not None:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="SCAN 报告不应提供 finding_id",
        )

    if normalized_report_type == ReportType.FINDING.value and not findings:
        raise AppError(
            code="REPORT_NO_FINDINGS",
            status_code=409,
            message="当前扫描任务下没有可生成报告的漏洞",
        )

    return PreparedReportSelection(
        report_type=normalized_report_type,
        scan_job=scan_job,
        findings=findings,
        finding=target_finding,
        template_key=template_key,
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
        raw_finding_id = payload.get("finding_id")
        selection = prepare_report_selection(
            session,
            project_id=job.project_id,
            version_id=job.version_id,
            job_id=_coerce_required_uuid(
                payload.get("scan_job_id"), field_name="scan_job_id"
            ),
            report_type=str(payload.get("report_type") or ""),
            finding_id=(
                _coerce_optional_uuid(raw_finding_id, field_name="finding_id")
                if raw_finding_id not in {None, ""}
                else None
            ),
        )
        generated_report_ids: list[str] = []
        generated_items: list[dict[str, object]] = []
        failed_items: list[dict[str, object]] = []

        reset_report_job_root(report_job_id=job.id)
        _set_report_job_running(session, job=job, stage=ReportJobStage.PREPARE.value)
        job.result_summary = {
            "report_type": selection.report_type,
            "template_key": selection.template_key,
            "scan_job_id": str(selection.scan_job.id),
            "finding_count": selection.finding_count,
            "generated_count": 0,
            "failed_count": 0,
            "target_finding_id": (
                str(selection.target_finding_id)
                if selection.target_finding_id is not None
                else None
            ),
        }
        _append_report_log(
            report_job_id=job.id,
            stage=ReportJobStage.PREPARE.value,
            message=(
                f"prepare report job, report_type={selection.report_type}, "
                f"finding_count={selection.finding_count}, scan_job_id={selection.scan_job.id}"
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

        report: Report | None = None
        object_key: str | None = None
        generated_at = utc_now()
        try:
            report = Report(
                project_id=job.project_id,
                version_id=job.version_id,
                job_id=selection.scan_job.id,
                report_job_id=job.id,
                finding_id=selection.target_finding_id,
                report_type=selection.report_type,
                status=ReportStatus.DRAFT.value,
                format=str(options["format"]),
                created_by=job.created_by,
            )
            session.add(report)
            session.flush()

            if selection.report_type == ReportType.SCAN.value:
                report_title = _build_scan_report_title(scan_job=selection.scan_job)
                content = _render_scan_report_markdown(
                    session,
                    report_id=report.id,
                    scan_job=selection.scan_job,
                    findings=selection.findings,
                    options=options,
                    ai_by_finding=ai_by_finding,
                    generated_at=generated_at,
                )
                summary_text = _build_scan_report_summary(
                    scan_job=selection.scan_job,
                    findings=selection.findings,
                )
            else:
                target_finding = selection.finding
                if target_finding is None:
                    raise AppError(
                        code="REPORT_NO_FINDINGS",
                        status_code=409,
                        message="当前扫描任务下没有可生成报告的漏洞",
                    )
                presentation = build_finding_presentation(
                    version_id=target_finding.version_id,
                    rule_key=target_finding.rule_key,
                    vuln_type=target_finding.vuln_type,
                    source_file=target_finding.source_file,
                    source_line=target_finding.source_line,
                    file_path=target_finding.file_path,
                    line_start=target_finding.line_start,
                )
                report_title = _build_finding_report_title(
                    finding=target_finding,
                    vuln_display_name=presentation.get("vuln_display_name"),
                )
                content = _render_finding_report_markdown(
                    session,
                    report_id=report.id,
                    finding=target_finding,
                    scan_job=selection.scan_job,
                    options=options,
                    ai_assessment=ai_by_finding.get(target_finding.id),
                    generated_at=generated_at,
                )
                summary_text = _build_finding_report_summary(
                    finding=target_finding,
                    vuln_display_name=presentation.get("vuln_display_name"),
                    entry_display=presentation.get("entry_display"),
                )

            file_name = _build_report_filename(
                report_type=selection.report_type,
                report_title=report_title,
                scan_job=selection.scan_job,
                finding=selection.finding,
            )
            object_key = build_generated_report_object_key(
                report_job_id=job.id,
                filename=file_name,
            )
            write_report_text(object_key=object_key, content=content)
            report.object_key = object_key
            report.title = report_title
            report.template_key = selection.template_key
            report.summary_text = summary_text
            session.flush()

            generated_report_ids.append(str(report.id))
            generated_items.append(
                {
                    "report_id": str(report.id),
                    "report_type": selection.report_type,
                    "finding_id": (
                        str(selection.target_finding_id)
                        if selection.target_finding_id is not None
                        else None
                    ),
                    "file_name": file_name,
                    "title": report_title,
                    "object_key": object_key,
                    "template_key": selection.template_key,
                    "status": "SUCCEEDED",
                }
            )
            _append_report_log(
                report_job_id=job.id,
                stage=ReportJobStage.RENDER.value,
                message=(
                    f"[render] generated report_type={selection.report_type}, report_id={report.id}, "
                    f"finding_count={selection.finding_count}"
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
                    "report_type": selection.report_type,
                    "finding_id": (
                        str(selection.target_finding_id)
                        if selection.target_finding_id is not None
                        else None
                    ),
                    "status": "FAILED",
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
            _append_report_log(
                report_job_id=job.id,
                stage=ReportJobStage.RENDER.value,
                message=f"[render] failed report_type={selection.report_type}, code={exc.code}",
                project_id=job.project_id,
                db=session,
            )
        except Exception as exc:
            _cleanup_failed_report_attempt(
                session, report=report, object_key=object_key
            )
            failed_items.append(
                {
                    "report_type": selection.report_type,
                    "finding_id": (
                        str(selection.target_finding_id)
                        if selection.target_finding_id is not None
                        else None
                    ),
                    "status": "FAILED",
                    "error_code": "REPORT_RENDER_FAILED",
                    "message": _truncate_text(str(exc) or exc.__class__.__name__, 512),
                }
            )
            _append_report_log(
                report_job_id=job.id,
                stage=ReportJobStage.RENDER.value,
                message=(
                    f"[render] failed report_type={selection.report_type}, code=REPORT_RENDER_FAILED"
                ),
                project_id=job.project_id,
                db=session,
            )

        job.result_summary = {
            **(job.result_summary or {}),
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

        partial = False
        manifest_payload = {
            "report_job_id": str(job.id),
            "report_type": selection.report_type,
            "template_key": selection.template_key,
            "scan_job_id": str(selection.scan_job.id),
            "scan_job_status": selection.scan_job.status,
            "finding_count": selection.finding_count,
            "generated_count": len(generated_items),
            "failed_count": len(failed_items),
            "partial": partial,
            "items": generated_items,
            "failures": failed_items,
        }
        manifest_text = json.dumps(manifest_payload, ensure_ascii=False, indent=2)
        manifest_object_key = build_report_manifest_object_key(report_job_id=job.id)
        write_report_text(object_key=manifest_object_key, content=manifest_text)

        _append_report_log(
            report_job_id=job.id,
            stage=ReportJobStage.PACKAGE.value,
            message=(
                f"[package] manifest_written=true, generated_count={len(generated_items)}, "
                f"failed_count={len(failed_items)}"
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
        generated_report_id = generated_report_ids[0] if generated_report_ids else None
        job.result_summary = {
            **(job.result_summary or {}),
            "generated_count": len(generated_items),
            "failed_count": len(failed_items),
            "partial": partial,
            "report_ids": generated_report_ids,
            "report_id": generated_report_id,
            "manifest_object_key": manifest_object_key,
            "bundle_object_key": None,
            "bundle_filename": None,
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
                "report_type": selection.report_type,
                "scan_job_id": str(selection.scan_job.id),
                "target_finding_id": (
                    str(selection.target_finding_id)
                    if selection.target_finding_id is not None
                    else None
                ),
                "finding_count": selection.finding_count,
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
    report: Report,
    *,
    finding: Finding | None = None,
    scan_job: Job | None = None,
    finding_count: int | None = None,
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

    resolved_title = str(getattr(report, "title", "") or "").strip() or None
    resolved_template_key = (
        str(getattr(report, "template_key", "") or "").strip() or None
    )
    resolved_summary_text = (
        str(getattr(report, "summary_text", "") or "").strip() or None
    )

    if resolved_title is None:
        if report.report_type == ReportType.SCAN.value:
            resolved_title = _build_scan_report_title(scan_job=scan_job)
        elif finding is not None:
            resolved_title = _build_finding_report_title(
                finding=finding,
                vuln_display_name=vuln_display_name,
            )
        else:
            resolved_title = "漏洞安全报告"

    if resolved_template_key is None:
        resolved_template_key = (
            REPORT_TEMPLATE_SCAN_V1
            if report.report_type == ReportType.SCAN.value
            else REPORT_TEMPLATE_FINDING_V1
        )

    if resolved_summary_text is None:
        if report.report_type == ReportType.SCAN.value:
            resolved_summary_text = _build_scan_report_summary(
                scan_job=scan_job,
                findings=[],
                finding_count_override=finding_count,
            )
        elif finding is not None:
            resolved_summary_text = _build_finding_report_summary(
                finding=finding,
                vuln_display_name=vuln_display_name,
                entry_display=entry_display,
            )

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
        title=resolved_title,
        template_key=resolved_template_key,
        summary_text=resolved_summary_text,
        finding_count=(
            finding_count
            if report.report_type == ReportType.SCAN.value
            else 1
            if finding is not None
            else None
        ),
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


def read_report_markdown_content(*, report: Report) -> str:
    _file_name, path = get_report_download_path(report=report)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppError(
            code="OBJECT_NOT_FOUND",
            status_code=404,
            message="报告内容不存在",
        ) from exc


def delete_report_record(db: Session, *, report: Report) -> dict[str, object]:
    deleted_report_file = False
    deleted_report_job_root = False
    deleted_report_job_files_count = 0
    deleted_task_log_index_count = 0
    deleted_log_files_count = 0
    remaining_report_count = 0
    report_job_id = report.report_job_id

    if report.object_key:
        deleted_report_file = delete_report_object(object_key=str(report.object_key))

    db.delete(report)
    db.flush()

    if report_job_id is not None:
        remaining_report_ids = db.scalars(
            select(Report.id)
            .where(Report.report_job_id == report_job_id)
            .order_by(Report.created_at.asc())
        ).all()
        remaining_report_count = len(remaining_report_ids)
        report_job = db.get(Job, report_job_id)
        if report_job is not None:
            _refresh_report_job_summary_after_delete(
                report_job=report_job,
                deleted_report_id=report.id,
                remaining_report_ids=remaining_report_ids,
            )

        if remaining_report_count > 0:
            manifest_object_key = _resolve_report_job_manifest_object_key(
                report_job_id=report_job_id,
                report_job=report_job,
            )
            if manifest_object_key is not None:
                delete_report_object(object_key=manifest_object_key)

        if remaining_report_count == 0:
            root_cleanup = delete_report_job_root(report_job_id=report_job_id)
            deleted_report_job_root = bool(root_cleanup.get("deleted"))
            deleted_report_job_files_count = int(
                root_cleanup.get("deleted_files_count", 0)
            )
            log_summary = delete_task_logs(
                task_type=TaskLogType.REPORT.value,
                task_id=report_job_id,
                db=db,
            )
            deleted_task_log_index_count = int(
                log_summary.get("deleted_task_log_index_count", 0)
            )
            deleted_log_files_count = int(log_summary.get("deleted_log_files_count", 0))

    return {
        "ok": True,
        "report_id": report.id,
        "report_job_id": report_job_id,
        "remaining_report_count": remaining_report_count,
        "deleted_report_file": deleted_report_file,
        "deleted_report_job_root": deleted_report_job_root,
        "deleted_report_job_files_count": deleted_report_job_files_count,
        "deleted_task_log_index_count": deleted_task_log_index_count,
        "deleted_log_files_count": deleted_log_files_count,
    }


def _resolve_report_job_manifest_object_key(
    *, report_job_id: uuid.UUID, report_job: Job | None
) -> str | None:
    if report_job is not None and isinstance(report_job.result_summary, dict):
        stored = str(report_job.result_summary.get("manifest_object_key") or "").strip()
        if stored:
            return stored
    return build_report_manifest_object_key(report_job_id=report_job_id)


def _refresh_report_job_summary_after_delete(
    *,
    report_job: Job,
    deleted_report_id: uuid.UUID,
    remaining_report_ids: list[uuid.UUID],
) -> None:
    next_summary = dict(report_job.result_summary or {})
    remaining_ids = [str(item) for item in remaining_report_ids]
    next_summary["report_ids"] = remaining_ids
    next_summary["report_id"] = remaining_ids[0] if remaining_ids else None
    next_summary["generated_count"] = len(remaining_ids)
    next_summary["manifest_object_key"] = None
    next_summary["bundle_object_key"] = None
    next_summary["bundle_filename"] = None
    next_summary["last_deleted_report_id"] = str(deleted_report_id)
    next_summary["last_deleted_at"] = utc_now().isoformat()
    if not remaining_ids:
        next_summary["manual_cleanup"] = {
            "deleted_report_id": str(deleted_report_id),
            "deleted_at": utc_now().isoformat(),
            "remaining_report_count": 0,
        }
    report_job.result_summary = next_summary


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


def _coerce_optional_uuid(value: object, *, field_name: str) -> uuid.UUID:
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
    *,
    report_type: str,
    report_title: str,
    scan_job: Job,
    finding: Finding | None,
) -> str:
    if report_type == ReportType.SCAN.value:
        return f"scan_report_{str(scan_job.id).split('-', 1)[0]}_{_slugify(report_title)}.md"
    if finding is None:
        return f"report_{_slugify(report_title)}.md"
    severity = str(finding.severity or "").strip().lower() or "unknown"
    short_id = str(finding.id).split("-", 1)[0]
    return f"finding_report_{severity}_{_slugify(report_title)}_{short_id}.md"


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


def _build_scan_report_title(*, scan_job: Job | None) -> str:
    if scan_job is None:
        return "扫描安全报告"
    return f"扫描安全报告（任务 {str(scan_job.id).split('-', 1)[0]}）"


def _build_finding_report_title(
    *, finding: Finding, vuln_display_name: str | None
) -> str:
    display_name = vuln_display_name or finding.vuln_type or finding.rule_key or "漏洞"
    return f"{display_name} 单漏洞安全报告"


def _format_severity_label(severity: str | None) -> str:
    normalized = str(severity or "").strip().upper()
    return SEVERITY_LABELS.get(normalized, normalized or "未评级")


def _sort_findings_for_report(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda item: (
            -SEVERITY_PRIORITY.get(str(item.severity or "").upper(), 0),
            str(item.created_at),
            str(item.id),
        ),
    )


def _count_findings_by_severity(findings: list[Finding]) -> dict[str, int]:
    counts = {"HIGH": 0, "MED": 0, "LOW": 0}
    for item in findings:
        severity = str(item.severity or "").upper()
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _build_top_vulnerability_lines(findings: list[Finding]) -> list[str]:
    type_counts: dict[str, int] = {}
    for item in findings:
        presentation = build_finding_presentation(
            version_id=item.version_id,
            rule_key=item.rule_key,
            vuln_type=item.vuln_type,
            source_file=item.source_file,
            source_line=item.source_line,
            file_path=item.file_path,
            line_start=item.line_start,
        )
        label = (
            presentation.get("vuln_display_name")
            or item.vuln_type
            or item.rule_key
            or "未知漏洞"
        )
        type_counts[label] = type_counts.get(label, 0) + 1
    ordered = sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    return [f"- {label}: {count} 条" for label, count in ordered]


def _build_scan_report_summary(
    *,
    scan_job: Job | None,
    findings: list[Finding],
    finding_count_override: int | None = None,
) -> str:
    finding_count = (
        finding_count_override if finding_count_override is not None else len(findings)
    )
    severity_counts = _count_findings_by_severity(findings)
    high_count = severity_counts.get("HIGH", 0)
    if finding_count <= 0:
        return "本次扫描未发现已记录漏洞，可作为当前版本的安全基线。"
    top_label = _build_top_vulnerability_lines(findings)
    top_fragment = top_label[0][2:] if top_label else "暂无明显集中类型"
    job_label = str(scan_job.id).split("-", 1)[0] if scan_job is not None else "-"
    return (
        f"任务 {job_label} 共汇总 {finding_count} 条漏洞，其中高危 {high_count} 条；"
        f"当前最集中的问题类型为 {top_fragment}。"
    )


def _build_finding_report_summary(
    *,
    finding: Finding,
    vuln_display_name: str | None,
    entry_display: str | None,
) -> str:
    display_name = vuln_display_name or finding.vuln_type or finding.rule_key or "漏洞"
    location = entry_display or _format_location(finding.file_path, finding.line_start)
    return (
        f"聚焦 {display_name}，风险等级为 {_format_severity_label(finding.severity)}，"
        f"影响入口或位置为 {location or '-'}。"
    )


def _build_finding_impact_text(
    *, finding: Finding, vuln_display_name: str | None
) -> str:
    vuln_type = str(finding.vuln_type or "").strip().upper()
    base_hint = VULNERABILITY_IMPACT_HINTS.get(
        vuln_type,
        "该问题可能影响系统输入校验、数据访问边界或敏感功能调用，需要结合业务场景尽快确认。",
    )
    severity_text = _format_severity_label(finding.severity)
    display_name = (
        vuln_display_name or finding.vuln_type or finding.rule_key or "该漏洞"
    )
    return f"{display_name} 当前被评估为{severity_text}问题。{base_hint}"


def _build_finding_remediation_lines(finding: Finding) -> list[str]:
    vuln_type = str(finding.vuln_type or "").strip().upper()
    lines = VULNERABILITY_REMEDIATION_HINTS.get(vuln_type)
    if lines:
        return lines
    return [
        "优先确认受影响输入、关键调用点和权限边界，避免问题继续向下游扩散。",
        "结合代码职责补充校验、编码、鉴权或隔离措施，并在修复后重新复扫验证。",
    ]


def _build_finding_evidence_lines(
    *,
    finding: Finding,
    presentation: dict[str, str | None],
    path_lines: list[str],
) -> list[str]:
    lines = [
        f"- 入口或受影响位置：{presentation.get('entry_display') or _format_location(finding.file_path, finding.line_start) or '-'}",
        f"- 主要受影响代码位置：{_format_location(finding.file_path, finding.line_start)}",
    ]
    if finding.source_file or finding.source_line:
        lines.append(
            f"- 可疑输入源位置：{_format_location(finding.source_file, finding.source_line)}"
        )
    if finding.sink_file or finding.sink_line:
        lines.append(
            f"- 危险汇聚点位置：{_format_location(finding.sink_file, finding.sink_line)}"
        )
    if finding.has_path and path_lines:
        lines.append(f"- 已记录传播链路，当前展示 {len(path_lines)} 个关键步骤。")
    elif finding.has_path:
        lines.append("- 系统标记存在传播链路，但当前未取到可展示的持久化步骤。")
    else:
        lines.append("- 当前未记录完整传播链路，需结合源码进一步确认。")
    return lines


def _build_ai_review_lines(ai_assessment: FindingAIAssessment | None) -> list[str]:
    if ai_assessment is None:
        return ["- 当前没有可用的 AI 研判结论。"]
    summary = build_finding_ai_review_summary(ai_assessment)
    verdict = summary.get("verdict") or "-"
    confidence = summary.get("confidence") or "-"
    status = summary.get("status") or "-"
    updated_at = summary.get("updated_at") or "-"
    lines = [
        f"- 研判状态：{status}",
        f"- 结论倾向：{verdict}",
        f"- 置信度：{confidence}",
        f"- 最近更新时间：{updated_at}",
    ]
    response_text = str(ai_assessment.response_text or "").strip()
    if response_text:
        lines.append(f"- 研判摘要：{_truncate_text(response_text, 240)}")
    return lines


def _append_code_snippet_section(lines: list[str], *, finding: Finding) -> None:
    snippets = _load_report_snippets(finding=finding)
    lines.extend(["### 代码片段", ""])
    if not snippets:
        lines.extend(["- 当前没有可用的源码片段。", ""])
        return
    for snippet in snippets:
        lines.extend(
            [
                f"#### {snippet['label']}",
                "",
                f"- 文件：`{snippet['file_path']}`",
                f"- 行号范围：`{snippet['start_line']}-{snippet['end_line']}`",
                "",
                f"```{snippet['language']}",
                str(snippet["content"]),
                "```",
                "",
            ]
        )


def _append_finding_technical_appendix(
    lines: list[str],
    *,
    db: Session,
    finding: Finding,
    ai_assessment: FindingAIAssessment | None,
    options: dict[str, object],
) -> None:
    path_lines = _load_persisted_path_lines(db, finding_id=finding.id)
    lines.extend(["## 五、技术附录", "", "### 路径与定位", ""])
    if path_lines:
        lines.extend([f"- {item}" for item in path_lines])
    else:
        lines.append("- 当前没有可展示的持久化路径步骤。")
    lines.append("")

    if bool(options.get("include_code_snippets")):
        _append_code_snippet_section(lines, finding=finding)

    if bool(options.get("include_ai_sections")):
        lines.extend(["### AI 辅助研判", ""])
        lines.extend(_build_ai_review_lines(ai_assessment))
        lines.append("")

    lines.extend(
        [
            "### 原始证据（技术核验用）",
            "",
            _render_json_code_block(finding.evidence_json, language="json"),
            "",
        ]
    )


def _render_scan_report_markdown(
    db: Session,
    *,
    report_id: uuid.UUID,
    scan_job: Job,
    findings: list[Finding],
    options: dict[str, object],
    ai_by_finding: dict[uuid.UUID, FindingAIAssessment],
    generated_at: datetime,
) -> str:
    ordered_findings = _sort_findings_for_report(findings)
    severity_counts = _count_findings_by_severity(ordered_findings)
    top_vulnerability_lines = _build_top_vulnerability_lines(ordered_findings)
    lines: list[str] = [
        f"# {_build_scan_report_title(scan_job=scan_job)}",
        "",
        "## 一、报告概况",
        "",
        f"- 报告 ID：`{report_id}`",
        f"- 生成时间：`{generated_at.isoformat()}`",
        f"- 来源扫描任务：`{scan_job.id}`",
        f"- 扫描任务状态：`{scan_job.status}`",
        f"- 漏洞总数：`{len(ordered_findings)}`",
        "- 报告定位：前半部分给管理者/老师看结论，后半部分给开发与安全人员看技术细节。",
        "",
        "## 二、管理摘要",
        "",
        _build_scan_report_summary(scan_job=scan_job, findings=ordered_findings),
        "",
    ]
    if scan_job.status != JobStatus.SUCCEEDED.value:
        lines.extend(
            [
                "> 说明：源扫描任务并非成功结束状态，报告内容可能存在部分结果或缺失项。",
                "",
            ]
        )

    lines.extend(
        [
            "## 三、风险总览",
            "",
            f"- 高危：{severity_counts.get('HIGH', 0)} 条",
            f"- 中危：{severity_counts.get('MED', 0)} 条",
            f"- 低危：{severity_counts.get('LOW', 0)} 条",
            "",
            "### 主要漏洞类型",
            "",
        ]
    )
    if top_vulnerability_lines:
        lines.extend(top_vulnerability_lines)
    else:
        lines.append("- 本次扫描未记录到漏洞类型。")
    lines.append("")

    lines.extend(["## 四、优先修复建议", ""])
    if not ordered_findings:
        lines.extend(
            [
                "1. 当前未发现已记录漏洞，建议将本报告作为基线并在后续版本持续复扫。",
                "2. 保持依赖更新、凭据治理和输入校验等常规安全措施，避免基线回退。",
                "",
            ]
        )
    else:
        for index, finding in enumerate(ordered_findings[:3], start=1):
            presentation = build_finding_presentation(
                version_id=finding.version_id,
                rule_key=finding.rule_key,
                vuln_type=finding.vuln_type,
                source_file=finding.source_file,
                source_line=finding.source_line,
                file_path=finding.file_path,
                line_start=finding.line_start,
            )
            lines.append(
                f"{index}. 优先处理 {presentation.get('vuln_display_name') or finding.vuln_type or finding.rule_key}，"
                f"其风险等级为 {_format_severity_label(finding.severity)}，"
                f"位置位于 {presentation.get('entry_display') or _format_location(finding.file_path, finding.line_start) or '-'}。"
            )
        lines.append("")

    lines.extend(["## 五、重点问题概览", ""])
    if not ordered_findings:
        lines.extend(["- 当前没有需要展开说明的漏洞项。", ""])
    else:
        for index, finding in enumerate(ordered_findings[:5], start=1):
            presentation = build_finding_presentation(
                version_id=finding.version_id,
                rule_key=finding.rule_key,
                vuln_type=finding.vuln_type,
                source_file=finding.source_file,
                source_line=finding.source_line,
                file_path=finding.file_path,
                line_start=finding.line_start,
            )
            lines.extend(
                [
                    f"### {index}. {presentation.get('vuln_display_name') or finding.vuln_type or finding.rule_key}",
                    "",
                    f"- 风险等级：{_format_severity_label(finding.severity)}",
                    f"- 影响位置：{presentation.get('entry_display') or _format_location(finding.file_path, finding.line_start) or '-'}",
                    f"- 风险说明：{_build_finding_impact_text(finding=finding, vuln_display_name=presentation.get('vuln_display_name'))}",
                    f"- 首要建议：{_build_finding_remediation_lines(finding)[0]}",
                    "",
                ]
            )

    lines.extend(["## 六、技术附录", ""])
    if not ordered_findings:
        lines.extend(["- 本次扫描没有生成需要附录展开的漏洞技术细节。", ""])
    else:
        for index, finding in enumerate(ordered_findings, start=1):
            presentation = build_finding_presentation(
                version_id=finding.version_id,
                rule_key=finding.rule_key,
                vuln_type=finding.vuln_type,
                source_file=finding.source_file,
                source_line=finding.source_line,
                file_path=finding.file_path,
                line_start=finding.line_start,
            )
            path_lines = _load_persisted_path_lines(db, finding_id=finding.id)
            lines.extend(
                [
                    f"### {index}. {presentation.get('vuln_display_name') or finding.vuln_type or finding.rule_key}",
                    "",
                    f"- 风险等级：{_format_severity_label(finding.severity)}",
                    f"- 漏洞状态：{finding.status}",
                    f"- 规则标识：`{finding.rule_key}`",
                    f"- 入口或位置：{presentation.get('entry_display') or _format_location(finding.file_path, finding.line_start) or '-'}",
                    "",
                    "#### 证据摘要",
                    "",
                ]
            )
            lines.extend(
                _build_finding_evidence_lines(
                    finding=finding,
                    presentation=presentation,
                    path_lines=path_lines,
                )
            )
            lines.extend(
                [
                    "",
                    "#### 业务影响",
                    "",
                    _build_finding_impact_text(
                        finding=finding,
                        vuln_display_name=presentation.get("vuln_display_name"),
                    ),
                    "",
                    "#### 修复建议",
                    "",
                ]
            )
            lines.extend(
                [f"- {item}" for item in _build_finding_remediation_lines(finding)]
            )
            lines.append("")
            if bool(options.get("include_code_snippets")):
                _append_code_snippet_section(lines, finding=finding)
            if bool(options.get("include_ai_sections")):
                lines.extend(["#### AI 辅助研判", ""])
                lines.extend(_build_ai_review_lines(ai_by_finding.get(finding.id)))
                lines.append("")
            lines.extend(
                [
                    "#### 原始证据（技术核验用）",
                    "",
                    _render_json_code_block(finding.evidence_json, language="json"),
                    "",
                ]
            )

    return "\n".join(lines).strip() + "\n"


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
    path_lines = _load_persisted_path_lines(db, finding_id=finding.id)
    vuln_display_name = presentation.get("vuln_display_name")
    lines: list[str] = [
        f"# {_build_finding_report_title(finding=finding, vuln_display_name=vuln_display_name)}",
        "",
        "## 一、结论摘要",
        "",
        f"- 报告 ID：`{report_id}`",
        f"- 生成时间：`{generated_at.isoformat()}`",
        f"- 来源扫描任务：`{scan_job.id}`",
        f"- 漏洞名称：{vuln_display_name or '-'}",
        f"- 风险等级：{_format_severity_label(finding.severity)}",
        f"- 漏洞状态：{finding.status}",
        f"- 入口或位置：{presentation.get('entry_display') or _format_location(finding.file_path, finding.line_start) or '-'}",
        "",
        _build_finding_report_summary(
            finding=finding,
            vuln_display_name=vuln_display_name,
            entry_display=presentation.get("entry_display"),
        ),
        "",
        "## 二、业务影响",
        "",
        _build_finding_impact_text(
            finding=finding, vuln_display_name=vuln_display_name
        ),
        "",
        "## 三、证据摘要",
        "",
    ]
    lines.extend(
        _build_finding_evidence_lines(
            finding=finding,
            presentation=presentation,
            path_lines=path_lines,
        )
    )
    lines.append("")
    if scan_job.status != JobStatus.SUCCEEDED.value:
        lines.extend(
            [
                "> 说明：源扫描任务并非成功结束状态，当前证据可能是不完整结果，请结合源码进一步核验。",
                "",
            ]
        )

    lines.extend(["## 四、修复建议", ""])
    lines.extend([f"- {item}" for item in _build_finding_remediation_lines(finding)])
    lines.append("")

    _append_finding_technical_appendix(
        lines,
        db=db,
        finding=finding,
        ai_assessment=ai_assessment,
        options=options,
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
