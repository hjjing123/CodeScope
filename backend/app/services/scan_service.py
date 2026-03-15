from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    Finding,
    FindingPath,
    FindingPathEdge,
    FindingPathStep,
    FindingSeverity,
    FindingStatus,
    Job,
    JobFailureCategory,
    JobStep,
    JobStepStatus,
    JobStage,
    JobStatus,
    JobType,
    Project,
    TaskLogType,
    Version,
    VersionStatus,
    utc_now,
)
from app.services.path_graph_service import normalize_path_graph
from app.services.audit_service import append_audit_log
from app.services.artifact_service import delete_scan_job_artifacts
from app.services.finding_presentation_service import build_finding_presentation
from app.services.job_stream_service import append_job_stream_event
from app.services.rule_file_service import get_rules_by_keys, normalize_rule_selector
from app.services.scan_runtime_service import (
    acquire_scan_runtime_slot,
    release_scan_runtime_slot,
)
from app.services.source_location_service import normalize_graph_location
from app.services.scan_external import run_external_scan as run_external_scan_pipeline
from app.services.scan_external.builtin import cleanup_ephemeral_runtime_resources
from app.services.scan_external.context import resolve_external_path
from app.services.scan_external.neo4j_runner import drop_database_if_exists
from app.services.scan_external.runtime_metadata import load_runtime_metadata
from app.services.snapshot_storage_service import read_snapshot_file_context
from app.services.task_log_service import append_task_log, delete_task_logs
from app.services.trace_repair_service import (
    normalize_external_finding_candidate,
    process_external_finding_candidate,
    repair_external_finding_candidate,
)


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

SCAN_DELETE_TARGETS = {
    "logs",
    "artifacts",
    "workspace",
    "findings",
    "job_record",
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
    "SCAN_EXTERNAL_SOURCE_SEMANTIC_FAILED": "源码语义增强阶段失败，请检查语义增强脚本与图数据。",
    "SCAN_EXTERNAL_SOURCE_SEMANTIC_TIMEOUT": "源码语义增强阶段超时，请检查语义增强复杂度与超时配置。",
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

SCAN_STEP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("prepare", "源码准备"),
    ("joern", "Joern 解析与导图"),
    ("neo4j_import", "导入 Neo4j"),
    ("post_labels", "图增强"),
    ("source_semantic", "源码语义增强"),
    ("rules", "规则扫描"),
    ("aggregate", "结果聚合与落库"),
    ("ai", "结果标准化与 AI 摘要"),
    ("archive", "归档结果"),
    ("cleanup", "清理资源"),
)

FINDING_DRAFT_REQUIRED_KEYS: tuple[str, ...] = (
    "rule_key",
    "severity",
    "file_path",
    "line_start",
    "line_end",
    "source",
    "sink",
    "evidence",
    "trace_summary",
)

LLM_TEXT_MAX_LENGTH = 800
LLM_EVIDENCE_ITEM_MAX_LENGTH = 200
LLM_EVIDENCE_ITEMS_MAX_COUNT = 6
LLM_CODE_SNIPPET_MAX_LENGTH = 400

TERMINAL_STEP_STATUSES = {
    JobStepStatus.SUCCEEDED.value,
    JobStepStatus.FAILED.value,
    JobStepStatus.CANCELED.value,
}

STAGE_STEP_KEYS: dict[str, tuple[str, ...]] = {
    JobStage.PREPARE.value: ("prepare",),
    JobStage.ANALYZE.value: ("joern", "neo4j_import"),
    JobStage.QUERY.value: ("post_labels", "source_semantic", "rules"),
    JobStage.AGGREGATE.value: ("aggregate",),
    JobStage.AI.value: ("ai",),
    JobStage.CLEANUP.value: ("archive", "cleanup"),
}

FAILURE_STEP_BY_CODE: dict[str, str] = {
    "VERSION_NOT_READY": "prepare",
    "SCAN_EXTERNAL_JOERN_FAILED": "joern",
    "SCAN_EXTERNAL_JOERN_TIMEOUT": "joern",
    "SCAN_EXTERNAL_IMPORT_FAILED": "neo4j_import",
    "SCAN_EXTERNAL_IMPORT_TIMEOUT": "neo4j_import",
    "SCAN_EXTERNAL_POST_LABELS_FAILED": "post_labels",
    "SCAN_EXTERNAL_POST_LABELS_TIMEOUT": "post_labels",
    "SCAN_EXTERNAL_SOURCE_SEMANTIC_FAILED": "source_semantic",
    "SCAN_EXTERNAL_SOURCE_SEMANTIC_TIMEOUT": "source_semantic",
    "SCAN_EXTERNAL_RULES_FAILED": "rules",
    "SCAN_EXTERNAL_RULES_TIMEOUT": "rules",
    "SCAN_EXTERNAL_RESULT_MISSING": "aggregate",
    "SCAN_EXTERNAL_RESULT_INVALID": "aggregate",
}

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
    "SCAN_EXTERNAL_SOURCE_SEMANTIC_FAILED": JobFailureCategory.RULE.value,
    "SCAN_EXTERNAL_SOURCE_SEMANTIC_TIMEOUT": JobFailureCategory.RESOURCE.value,
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
    initialize_scan_job_steps(db, job_id=job.id)
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
    path = _absolute_settings_path(get_settings().scan_log_root) / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _scan_result_archive_path(*, job_id: uuid.UUID) -> Path:
    return _job_log_dir(job_id=job_id) / "scan_result.json"


def _build_scan_result_archive_payload(*, job: Job) -> dict[str, object]:
    return {
        "job_id": str(job.id),
        "project_id": str(job.project_id),
        "version_id": str(job.version_id),
        "job_type": str(job.job_type),
        "status": str(job.status),
        "stage": str(job.stage),
        "failure_code": job.failure_code,
        "failure_stage": job.failure_stage,
        "failure_category": job.failure_category,
        "failure_hint": job.failure_hint,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "result_summary": dict(job.result_summary or {}),
    }


def _write_scan_result_archive(*, job: Job) -> dict[str, object]:
    archive_path = _scan_result_archive_path(job_id=job.id)
    payload = _build_scan_result_archive_payload(job=job)
    archive_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "artifact": "scan_result",
        "path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
    }


def _tail_text(value: str | None, max_chars: int = 2000) -> str:
    normalized = str(value or "")
    if len(normalized) <= max_chars:
        return normalized
    return normalized[-max_chars:]


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


def _append_job_stream_event_safe(
    db: Session,
    *,
    job_id: uuid.UUID,
    project_id: uuid.UUID | None,
    event_type: str,
    payload: dict[str, object],
) -> None:
    try:
        append_job_stream_event(
            db,
            job_id=job_id,
            project_id=project_id,
            event_type=event_type,
            payload=payload,
        )
    except Exception:
        return


def _serialize_finding_record(finding: Finding) -> dict[str, object]:
    presentation = build_finding_presentation(
        version_id=finding.version_id,
        rule_key=finding.rule_key,
        vuln_type=finding.vuln_type,
        source_file=finding.source_file,
        source_line=finding.source_line,
        file_path=finding.file_path,
        line_start=finding.line_start,
    )
    return {
        "id": str(finding.id),
        "project_id": str(finding.project_id),
        "version_id": str(finding.version_id),
        "job_id": str(finding.job_id),
        "rule_key": finding.rule_key,
        "rule_version": finding.rule_version,
        "vuln_type": finding.vuln_type,
        "vuln_display_name": presentation.get("vuln_display_name"),
        "severity": finding.severity,
        "status": finding.status,
        "file_path": finding.file_path,
        "line_start": finding.line_start,
        "line_end": finding.line_end,
        "entry_display": presentation.get("entry_display"),
        "entry_kind": presentation.get("entry_kind"),
        "has_path": finding.has_path,
        "path_length": finding.path_length,
        "source_file": finding.source_file,
        "source_line": finding.source_line,
        "sink_file": finding.sink_file,
        "sink_line": finding.sink_line,
        "evidence_json": dict(finding.evidence_json or {}),
        "created_at": finding.created_at.isoformat() if finding.created_at else None,
    }


def _load_job_finding_snapshots(
    db: Session, *, job_id: uuid.UUID
) -> list[dict[str, object]]:
    rows = db.scalars(
        select(Finding)
        .where(Finding.job_id == job_id)
        .order_by(
            Finding.rule_key.asc(),
            Finding.file_path.asc().nullslast(),
            Finding.line_start.asc().nullslast(),
            Finding.created_at.asc(),
        )
    ).all()
    return [_serialize_finding_record(row) for row in rows]


def _scan_external_workspace_dir(*, job: Job) -> Path:
    return (
        _absolute_settings_path(get_settings().scan_workspace_root)
        / str(job.project_id)
        / str(job.id)
        / "external"
    )


def _absolute_path_without_resolve(path: Path | str) -> Path:
    normalized = Path(os.path.normpath(str(path)))
    if normalized.is_absolute():
        return normalized
    backend_root = Path(__file__).resolve().parents[2]
    return Path(os.path.normpath(str(backend_root / normalized)))


def _absolute_settings_path(path: Path | str) -> Path:
    return _absolute_path_without_resolve(path)


def _path_is_within_root(*, target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _release_scan_workspace(*, job: Job) -> dict[str, object]:
    workspace_dir = _absolute_path_without_resolve(
        _scan_external_workspace_dir(job=job)
    )
    workspace_root = _absolute_path_without_resolve(get_settings().scan_workspace_root)
    if not _path_is_within_root(target=workspace_dir, root=workspace_root):
        return {
            "workspace_dir": str(workspace_dir),
            "workspace_existed_before": workspace_dir.exists(),
            "workspace_exists_after": workspace_dir.exists(),
            "workspace_released": False,
            "workspace_cleanup_error": (
                "refused to delete workspace outside configured root: "
                f"workspace_dir={workspace_dir}, workspace_root={workspace_root}"
            ),
        }

    existed_before = workspace_dir.exists()
    error: str | None = None
    if existed_before:
        try:
            shutil.rmtree(workspace_dir)
        except Exception as exc:
            error = str(exc)

    released = not workspace_dir.exists()
    cleanup_cursor = workspace_dir.parent
    while released and cleanup_cursor.exists() and cleanup_cursor != workspace_root:
        try:
            cleanup_cursor.rmdir()
        except OSError:
            break
        cleanup_cursor = cleanup_cursor.parent

    return {
        "workspace_dir": str(workspace_dir),
        "workspace_existed_before": existed_before,
        "workspace_exists_after": workspace_dir.exists(),
        "workspace_released": released,
        "workspace_cleanup_error": error,
    }


def _load_external_runtime_metadata(*, job: Job) -> dict[str, object]:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    reports_dir = resolve_external_path(
        raw_value=str(settings.scan_external_reports_dir or ""),
        job=job,
        backend_root=backend_root,
    )
    if reports_dir is None:
        return {}
    return load_runtime_metadata(reports_dir=reports_dir)


def _cleanup_external_neo4j_database(
    *, job: Job, result_summary: dict[str, object] | None
) -> dict[str, object]:
    settings = get_settings()
    database_cleanup_enabled = bool(
        getattr(settings, "scan_external_neo4j_cleanup_enabled", False)
    )
    runtime = (
        result_summary.get("neo4j_runtime")
        if isinstance(result_summary, dict)
        else None
    )
    runtime_metadata = _load_external_runtime_metadata(job=job)
    if isinstance(runtime, dict) and runtime_metadata:
        runtime = {**runtime, **runtime_metadata}
    elif runtime is None and runtime_metadata:
        runtime = runtime_metadata
    database = ""
    uri = ""
    restart_mode = "none"
    container_name = ""
    data_mount = ""
    network_name = ""
    network_created_by_job = False
    if isinstance(runtime, dict):
        uri = str(runtime.get("uri") or "").strip()
        database = str(
            runtime.get("database") or runtime.get("import_database") or ""
        ).strip()
        restart_mode = str(runtime.get("restart_mode") or "none").strip().lower()
        container_name = str(runtime.get("container_name") or "").strip()
        data_mount = str(runtime.get("data_mount") or "").strip()
        network_name = str(runtime.get("network") or "").strip()
        network_created_by_job = bool(runtime.get("network_created_by_job"))

    ephemeral_runtime = restart_mode == "docker_ephemeral"
    cleanup_enabled = database_cleanup_enabled or ephemeral_runtime

    summary = {
        "enabled": cleanup_enabled,
        "uri": uri or None,
        "database": database or None,
        "restart_mode": restart_mode,
        "container_name": container_name or None,
        "data_mount": data_mount or None,
        "network": network_name or None,
        "network_created_by_job": network_created_by_job,
        "cleanup_attempted": False,
        "cleanup_succeeded": False,
        "cleanup_skipped_reason": None,
        "database_cleanup_attempted": False,
        "database_cleanup_succeeded": False,
        "container_cleanup_attempted": False,
        "container_cleanup_succeeded": False,
        "data_cleanup_attempted": False,
        "data_cleanup_succeeded": False,
        "network_cleanup_attempted": False,
        "network_cleanup_succeeded": False,
    }
    if ephemeral_runtime:
        runtime_cleanup = cleanup_ephemeral_runtime_resources(
            container_name=container_name or None,
            data_mount=data_mount or None,
            network_name=network_name or None,
            cleanup_network=network_created_by_job,
            deadline=time.monotonic() + 60,
        )
        summary.update(runtime_cleanup)

    if not cleanup_enabled:
        summary["cleanup_skipped_reason"] = "disabled"
        return summary
    if not database_cleanup_enabled:
        summary["cleanup_attempted"] = bool(
            summary["container_cleanup_attempted"]
            or summary["data_cleanup_attempted"]
            or summary["network_cleanup_attempted"]
        )
        summary["cleanup_succeeded"] = (
            bool(
                (
                    not summary["container_cleanup_attempted"]
                    or summary["container_cleanup_succeeded"]
                )
                and (
                    not summary["data_cleanup_attempted"]
                    or summary["data_cleanup_succeeded"]
                )
                and (
                    not summary["network_cleanup_attempted"]
                    or summary["network_cleanup_succeeded"]
                )
            )
            if summary["cleanup_attempted"]
            else False
        )
        if not summary["cleanup_attempted"]:
            summary["cleanup_skipped_reason"] = "database_cleanup_disabled"
        return summary
    if not database:
        summary["cleanup_skipped_reason"] = "database_missing"
        summary["cleanup_attempted"] = bool(
            summary["container_cleanup_attempted"]
            or summary["data_cleanup_attempted"]
            or summary["network_cleanup_attempted"]
        )
        summary["cleanup_succeeded"] = (
            bool(
                (
                    not summary["container_cleanup_attempted"]
                    or summary["container_cleanup_succeeded"]
                )
                and (
                    not summary["data_cleanup_attempted"]
                    or summary["data_cleanup_succeeded"]
                )
                and (
                    not summary["network_cleanup_attempted"]
                    or summary["network_cleanup_succeeded"]
                )
            )
            if summary["cleanup_attempted"]
            else False
        )
        return summary
    if database.lower() in {"neo4j", "system"}:
        summary["cleanup_skipped_reason"] = "protected_database"
        summary["cleanup_attempted"] = bool(
            summary["container_cleanup_attempted"]
            or summary["data_cleanup_attempted"]
            or summary["network_cleanup_attempted"]
        )
        summary["cleanup_succeeded"] = (
            bool(
                (
                    not summary["container_cleanup_attempted"]
                    or summary["container_cleanup_succeeded"]
                )
                and (
                    not summary["data_cleanup_attempted"]
                    or summary["data_cleanup_succeeded"]
                )
                and (
                    not summary["network_cleanup_attempted"]
                    or summary["network_cleanup_succeeded"]
                )
            )
            if summary["cleanup_attempted"]
            else False
        )
        return summary

    drop_database_if_exists(
        uri=uri or str(settings.scan_external_neo4j_uri or ""),
        user=str(settings.scan_external_neo4j_user or ""),
        password=str(settings.scan_external_neo4j_password or ""),
        database=database,
        connect_retry=int(settings.scan_external_neo4j_connect_retry),
        connect_wait_seconds=int(settings.scan_external_neo4j_connect_wait_seconds),
    )
    summary["database_cleanup_attempted"] = True
    summary["database_cleanup_succeeded"] = True
    summary["cleanup_attempted"] = True
    summary["cleanup_succeeded"] = bool(
        (
            not summary["container_cleanup_attempted"]
            or summary["container_cleanup_succeeded"]
        )
        and (not summary["data_cleanup_attempted"] or summary["data_cleanup_succeeded"])
        and (
            not summary["network_cleanup_attempted"]
            or summary["network_cleanup_succeeded"]
        )
        and summary["database_cleanup_succeeded"]
    )
    return summary


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

    initialize_scan_job_steps(db, job_id=job.id)
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
    result_summary = {
        **(job.result_summary or {}),
        "canceled": True,
    }
    try:
        job.result_summary = dict(result_summary)
        job.result_summary["archive"] = _write_scan_result_archive(job=job)
        result_summary["archive"] = job.result_summary.get("archive")
        _set_scan_step_status(
            db,
            job_id=job.id,
            step_key="archive",
            status=JobStepStatus.SUCCEEDED.value,
            commit=True,
        )
    except Exception as exc:
        _append_scan_log(
            job_id=job.id,
            stage=job.stage,
            message=f"扫描结果归档写入失败（不影响取消）: {exc}",
            project_id=job.project_id,
        )
    try:
        result_summary["neo4j_cleanup"] = _cleanup_external_neo4j_database(
            job=job, result_summary=result_summary
        )
    except Exception as exc:
        result_summary["neo4j_cleanup"] = {
            "enabled": True,
            "database": None,
            "cleanup_attempted": True,
            "cleanup_succeeded": False,
            "cleanup_skipped_reason": None,
            "error": str(exc),
        }
        _append_scan_log(
            job_id=job.id,
            stage=job.stage,
            message=f"Neo4j 清理失败（不影响取消）: {exc}",
            project_id=job.project_id,
        )
    cleanup_summary = _release_scan_workspace(job=job)
    result_summary["cleanup"] = cleanup_summary
    job.result_summary = dict(result_summary)
    _finalize_scan_steps(
        db,
        job_id=job.id,
        final_status=JobStatus.CANCELED.value,
        failure_code="SCAN_CANCELED",
        stage=job.stage,
    )
    _append_scan_log(
        job_id=job.id,
        stage=job.stage,
        message=(
            f"任务已取消。 workspace_released={cleanup_summary['workspace_released']}"
        ),
        project_id=job.project_id,
    )
    _append_job_stream_event_safe(
        db,
        job_id=job.id,
        project_id=job.project_id,
        event_type="done",
        payload={"status": JobStatus.CANCELED.value, "stage": job.stage},
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
    retry_payload.pop("scan_mode", None)
    retry_payload.pop("target_rule_id", None)
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
    initialize_scan_job_steps(db, job_id=retried_job.id)
    return retried_job


def normalize_scan_delete_targets(targets: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for raw_target in targets or []:
        normalized = str(raw_target or "").strip().lower()
        if not normalized:
            continue
        if normalized not in SCAN_DELETE_TARGETS:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="删除目标不合法",
                detail={"allowed_targets": sorted(SCAN_DELETE_TARGETS)},
            )
        if normalized not in cleaned:
            cleaned.append(normalized)
    if not cleaned:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="请至少选择一个删除目标",
            detail={"allowed_targets": sorted(SCAN_DELETE_TARGETS)},
        )
    return cleaned


def delete_scan_job(
    db: Session,
    *,
    job: Job,
    request_id: str,
    operator_user_id: uuid.UUID,
    targets: list[str],
) -> dict[str, object]:
    if job.job_type != JobType.SCAN.value:
        raise AppError(
            code="INVALID_ARGUMENT", status_code=422, message="仅支持删除扫描任务"
        )

    if job.status not in TERMINAL_SCAN_STATUSES:
        raise AppError(
            code="JOB_NOT_DELETABLE",
            status_code=409,
            message="仅允许删除已结束的扫描任务",
        )

    deleted_targets = normalize_scan_delete_targets(targets)
    effective_targets = list(deleted_targets)
    forced_targets: list[str] = []
    warnings: list[str] = []
    if "job_record" in effective_targets and "findings" not in effective_targets:
        effective_targets.append("findings")
        forced_targets.append("findings")
        warnings.append(
            "删除任务记录会级联删除本次扫描结果 Findings，已自动纳入删除范围。"
        )

    summary = {
        "deleted_targets": effective_targets,
        "forced_targets": forced_targets,
        "warnings": warnings,
        "deleted_findings_count": 0,
        "deleted_job_steps_count": 0,
        "deleted_task_log_index_count": 0,
        "deleted_log_files_count": 0,
        "deleted_archive_files_count": 0,
        "deleted_report_files_count": 0,
        "deleted_workspace_paths_count": 0,
        "deleted_job_record": False,
    }

    if "logs" in effective_targets:
        log_summary = delete_task_logs(
            task_type=TaskLogType.SCAN.value,
            task_id=job.id,
            db=db,
        )
        summary["deleted_task_log_index_count"] = int(
            log_summary.get("deleted_task_log_index_count", 0)
        )
        summary["deleted_log_files_count"] = int(
            log_summary.get("deleted_log_files_count", 0)
        )

    if "artifacts" in effective_targets:
        artifact_summary = delete_scan_job_artifacts(job=job)
        summary["deleted_archive_files_count"] = int(
            artifact_summary.get("deleted_archive_files_count", 0)
        )
        summary["deleted_report_files_count"] = int(
            artifact_summary.get("deleted_report_files_count", 0)
        )

    if "workspace" in effective_targets:
        workspace_summary = _delete_scan_workspace_for_cleanup(job=job)
        summary["deleted_workspace_paths_count"] = int(
            workspace_summary.get("deleted_workspace_paths_count", 0)
        )

    findings_count = 0
    if "findings" in effective_targets:
        findings_count = len(
            db.scalars(select(Finding.id).where(Finding.job_id == job.id)).all()
        )
        db.execute(delete(Finding).where(Finding.job_id == job.id))
        summary["deleted_findings_count"] = findings_count

    if "job_record" in effective_targets:
        summary["deleted_job_steps_count"] = len(
            db.scalars(select(JobStep.id).where(JobStep.job_id == job.id)).all()
        )
        db.delete(job)
        summary["deleted_job_record"] = True
    else:
        cleanup_detail = {
            "deleted_targets": effective_targets,
            "forced_targets": forced_targets,
            "deleted_at": utc_now().isoformat(),
        }
        if findings_count > 0:
            cleanup_detail["deleted_findings_count"] = findings_count
        next_summary = dict(job.result_summary or {})
        next_summary["manual_cleanup"] = cleanup_detail
        job.result_summary = next_summary

    append_audit_log(
        db,
        request_id=request_id,
        operator_user_id=operator_user_id,
        action="scan.deleted",
        resource_type="JOB",
        resource_id=str(job.id),
        project_id=job.project_id,
        detail_json={
            "targets": effective_targets,
            "forced_targets": forced_targets,
            "deleted_findings_count": summary["deleted_findings_count"],
            "deleted_job_record": summary["deleted_job_record"],
        },
    )
    db.commit()
    return summary


def initialize_scan_job_steps(db: Session, *, job_id: uuid.UUID) -> list[JobStep]:
    existing = db.scalars(select(JobStep).where(JobStep.job_id == job_id)).all()
    existing_keys = {item.step_key for item in existing}
    created: list[JobStep] = []
    for index, (step_key, display_name) in enumerate(SCAN_STEP_DEFINITIONS, start=1):
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


def _legacy_scan_workspace_dir(*, job: Job) -> Path:
    return Path(get_settings().scan_workspace_root) / str(job.id)


def _delete_scan_workspace_for_cleanup(*, job: Job) -> dict[str, object]:
    summary = _release_scan_workspace(job=job)
    deleted_workspace_paths_count = 1 if summary.get("workspace_existed_before") else 0

    legacy_workspace_dir = _legacy_scan_workspace_dir(job=job)
    external_workspace_dir = _scan_external_workspace_dir(job=job)
    same_as_external = False
    try:
        same_as_external = (
            legacy_workspace_dir.resolve() == external_workspace_dir.resolve()
        )
    except OSError:
        same_as_external = legacy_workspace_dir == external_workspace_dir

    if not same_as_external and legacy_workspace_dir.exists():
        try:
            shutil.rmtree(legacy_workspace_dir)
            deleted_workspace_paths_count += 1
        except Exception:
            pass

    return {
        **summary,
        "legacy_workspace_dir": str(legacy_workspace_dir),
        "deleted_workspace_paths_count": deleted_workspace_paths_count,
    }


def update_scan_job_step_status(
    db: Session,
    *,
    job_id: uuid.UUID,
    step_key: str,
    status: str,
    now: datetime | None = None,
) -> JobStep:
    normalized_status = (status or "").strip().lower()
    valid_statuses = {item.value for item in JobStepStatus}
    if normalized_status not in valid_statuses:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="步骤状态不合法",
            detail={"allowed_statuses": sorted(valid_statuses)},
        )

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

    timestamp = now or utc_now()
    step.status = normalized_status

    if normalized_status == JobStepStatus.PENDING.value:
        step.started_at = None
        step.finished_at = None
        step.duration_ms = None
    elif normalized_status == JobStepStatus.RUNNING.value:
        if step.started_at is None:
            step.started_at = timestamp
        step.finished_at = None
        step.duration_ms = None
    elif normalized_status in TERMINAL_STEP_STATUSES:
        if step.started_at is None:
            step.started_at = timestamp
        step.finished_at = timestamp
        step.duration_ms = _duration_ms_between(
            start=step.started_at,
            end=step.finished_at,
        )

    db.flush()
    return step


def _coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _duration_ms_between(*, start: datetime, end: datetime) -> int:
    duration = _coerce_utc_datetime(end) - _coerce_utc_datetime(start)
    return max(0, int(duration.total_seconds() * 1000))


def list_scan_job_steps(db: Session, *, job_id: uuid.UUID) -> list[JobStep]:
    return db.scalars(
        select(JobStep)
        .where(JobStep.job_id == job_id)
        .order_by(JobStep.step_order.asc(), JobStep.created_at.asc())
    ).all()


def build_scan_progress_payload(
    *, steps: list[JobStep], job_status: str | None = None
) -> dict[str, object]:
    total = len(steps)
    completed = sum(1 for item in steps if item.status == JobStepStatus.SUCCEEDED.value)
    running = next(
        (item for item in steps if item.status == JobStepStatus.RUNNING.value), None
    )
    current_step = running.step_key if running is not None else None
    if current_step is None:
        latest_terminal = next(
            (item for item in reversed(steps) if item.status in TERMINAL_STEP_STATUSES),
            None,
        )
        if (
            latest_terminal is not None
            and latest_terminal.status != JobStepStatus.SUCCEEDED.value
        ):
            current_step = latest_terminal.step_key
    percent = 100 if total == 0 else int((completed / total) * 100)
    if total > 0 and completed >= total and job_status not in TERMINAL_SCAN_STATUSES:
        percent = 99
        if current_step is None:
            current_step = steps[-1].step_key
    return {
        "total_steps": total,
        "completed_steps": completed,
        "percent": percent,
        "current_step": current_step,
    }


def build_scan_steps_payload(*, steps: list[JobStep]) -> list[dict[str, object]]:
    return [
        {
            "step_key": item.step_key,
            "display_name": item.display_name,
            "step_order": item.step_order,
            "status": item.status,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "duration_ms": item.duration_ms,
        }
        for item in steps
    ]


def _set_scan_step_status(
    db: Session,
    *,
    job_id: uuid.UUID,
    step_key: str,
    status: str,
    commit: bool = False,
) -> None:
    step = update_scan_job_step_status(
        db,
        job_id=job_id,
        step_key=step_key,
        status=status,
    )
    job = db.get(Job, job_id)
    _append_job_stream_event_safe(
        db,
        job_id=job_id,
        project_id=job.project_id if job is not None else None,
        event_type="step_status",
        payload={
            "step_key": step_key,
            "status": status,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            "duration_ms": step.duration_ms,
        },
    )
    if commit:
        db.commit()


def _mark_scan_stage_started(db: Session, *, job: Job, stage: str) -> None:
    _set_scan_job_running(db, job=job, stage=stage)
    stage_steps = STAGE_STEP_KEYS.get(stage, ())
    for step_key in stage_steps:
        step = db.scalar(
            select(JobStep).where(
                JobStep.job_id == job.id, JobStep.step_key == step_key
            )
        )
        if step is None or step.status in TERMINAL_STEP_STATUSES:
            continue
        update_scan_job_step_status(
            db,
            job_id=job.id,
            step_key=step_key,
            status=JobStepStatus.RUNNING.value,
        )
    db.commit()


def _running_scan_step_key(db: Session, *, job_id: uuid.UUID) -> str | None:
    running = db.scalar(
        select(JobStep)
        .where(JobStep.job_id == job_id, JobStep.status == JobStepStatus.RUNNING.value)
        .order_by(JobStep.step_order.desc())
    )
    if running is None:
        return None
    return running.step_key


def _failure_step_key(
    *, failure_code: str, stage: str, db: Session, job_id: uuid.UUID
) -> str | None:
    mapped = FAILURE_STEP_BY_CODE.get(failure_code)
    if mapped:
        return mapped
    running_step = _running_scan_step_key(db, job_id=job_id)
    if running_step:
        return running_step
    stage_steps = STAGE_STEP_KEYS.get(stage, ())
    if stage_steps:
        return stage_steps[-1]
    return None


def _finalize_scan_steps(
    db: Session,
    *,
    job_id: uuid.UUID,
    final_status: str,
    failure_code: str | None = None,
    stage: str | None = None,
) -> None:
    steps = list_scan_job_steps(db, job_id=job_id)
    if not steps:
        return

    if final_status == JobStatus.SUCCEEDED.value:
        for item in steps:
            if item.status != JobStepStatus.SUCCEEDED.value:
                update_scan_job_step_status(
                    db,
                    job_id=job_id,
                    step_key=item.step_key,
                    status=JobStepStatus.SUCCEEDED.value,
                )
        db.flush()
        return

    if final_status == JobStatus.CANCELED.value:
        for item in steps:
            if item.status in {
                JobStepStatus.PENDING.value,
                JobStepStatus.RUNNING.value,
            }:
                update_scan_job_step_status(
                    db,
                    job_id=job_id,
                    step_key=item.step_key,
                    status=JobStepStatus.CANCELED.value,
                )
        db.flush()
        return

    failure_step = _failure_step_key(
        failure_code=failure_code or "",
        stage=stage or "",
        db=db,
        job_id=job_id,
    )
    for item in steps:
        if item.step_key == failure_step:
            update_scan_job_step_status(
                db,
                job_id=job_id,
                step_key=item.step_key,
                status=JobStepStatus.FAILED.value,
            )
            continue
        if item.status in {
            JobStepStatus.PENDING.value,
            JobStepStatus.RUNNING.value,
        }:
            update_scan_job_step_status(
                db,
                job_id=job_id,
                step_key=item.step_key,
                status=JobStepStatus.CANCELED.value,
            )
    db.flush()


def run_scan_job(*, job_id: uuid.UUID, db: Session | None = None) -> None:
    owns_db = db is None
    session = db or SessionLocal()
    slot_acquired = False
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

        engine_mode = (get_settings().scan_engine_mode or "stub").strip().lower()
        if engine_mode == "external":
            acquire_scan_runtime_slot(
                job_id=job.id,
                db_bind=session.get_bind(),
                on_wait=lambda rounds: (
                    _append_scan_log(
                        job_id=job.id,
                        stage=JobStage.PREPARE.value,
                        message=(
                            "等待 Neo4j 运行槽位中..."
                            f" round={rounds}, max_slots={get_settings().scan_external_runtime_max_slots}"
                        ),
                        project_id=job.project_id,
                    )
                    if rounds == 1 or rounds % 10 == 0
                    else None
                ),
            )
            slot_acquired = True

        initialize_scan_job_steps(session, job_id=job.id)
        _mark_scan_stage_started(session, job=job, stage=JobStage.PREPARE.value)

        if engine_mode == "external":
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="prepare",
                status=JobStepStatus.SUCCEEDED.value,
                commit=True,
            )
            _mark_scan_stage_started(session, job=job, stage=JobStage.ANALYZE.value)
            execution = _run_external_scan(job=job, db=session)
        else:
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="prepare",
                status=JobStepStatus.SUCCEEDED.value,
                commit=True,
            )
            _mark_scan_stage_started(session, job=job, stage=JobStage.ANALYZE.value)
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="joern",
                status=JobStepStatus.SUCCEEDED.value,
            )
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="neo4j_import",
                status=JobStepStatus.SUCCEEDED.value,
                commit=True,
            )
            _mark_scan_stage_started(session, job=job, stage=JobStage.QUERY.value)
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="post_labels",
                status=JobStepStatus.SUCCEEDED.value,
            )
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="source_semantic",
                status=JobStepStatus.SUCCEEDED.value,
            )
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="rules",
                status=JobStepStatus.RUNNING.value,
                commit=True,
            )
            execution = _run_stub_scan(job=job)
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="rules",
                status=JobStepStatus.SUCCEEDED.value,
                commit=True,
            )

        _mark_scan_stage_started(session, job=job, stage=JobStage.AGGREGATE.value)
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

        finding_drafts = _normalize_finding_drafts(
            findings=execution.findings,
            rule_meta_by_key=rule_meta_by_key,
        )
        finding_drafts = _attach_code_contexts(job=job, finding_drafts=finding_drafts)
        code_context_ready = sum(
            1 for item in finding_drafts if isinstance(item.get("code_context"), dict)
        )
        if engine_mode != "external":
            for draft in finding_drafts:
                session.add(_create_finding_model_from_draft(job=job, draft=draft))
        if len(finding_drafts) < len(execution.findings):
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.AGGREGATE.value,
                message=(
                    "发现非标准化结果已跳过: "
                    f"raw={len(execution.findings)}, normalized={len(finding_drafts)}"
                ),
            )

        _set_scan_step_status(
            session,
            job_id=job.id,
            step_key="aggregate",
            status=JobStepStatus.SUCCEEDED.value,
            commit=True,
        )
        _mark_scan_stage_started(session, job=job, stage=JobStage.AI.value)
        llm_enriched_drafts = _attach_ai_payloads(finding_drafts)
        execution.result_summary["finding_drafts"] = llm_enriched_drafts
        execution.result_summary["normalized_finding_count"] = len(finding_drafts)
        execution.result_summary["ai_summary"] = {
            "normalized_findings": len(finding_drafts),
            "code_context_ready": code_context_ready,
            "prompt_blocks_ready": len(llm_enriched_drafts),
        }
        _append_scan_log(
            job_id=job.id,
            stage=JobStage.AI.value,
            message=(
                "结果标准化与 AI 摘要完成: "
                f"normalized_findings={len(finding_drafts)}, "
                f"code_context_ready={code_context_ready}, "
                f"prompt_blocks_ready={len(llm_enriched_drafts)}"
            ),
            project_id=job.project_id,
        )
        _set_scan_step_status(
            session,
            job_id=job.id,
            step_key="ai",
            status=JobStepStatus.SUCCEEDED.value,
            commit=True,
        )
        _mark_scan_stage_started(session, job=job, stage=JobStage.CLEANUP.value)
        job_result_summary = dict(execution.result_summary)
        try:
            job.result_summary = dict(job_result_summary)
            job_result_summary["archive"] = _write_scan_result_archive(job=job)
            _set_scan_step_status(
                session,
                job_id=job.id,
                step_key="archive",
                status=JobStepStatus.SUCCEEDED.value,
                commit=True,
            )
        except Exception as exc:
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.CLEANUP.value,
                message=f"扫描结果归档写入失败（不影响任务成功）: {exc}",
                project_id=job.project_id,
            )
        try:
            job_result_summary["neo4j_cleanup"] = _cleanup_external_neo4j_database(
                job=job, result_summary=job_result_summary
            )
        except Exception as exc:
            job_result_summary["neo4j_cleanup"] = {
                "enabled": True,
                "database": None,
                "cleanup_attempted": True,
                "cleanup_succeeded": False,
                "cleanup_skipped_reason": None,
                "error": str(exc),
            }
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.CLEANUP.value,
                message=f"Neo4j 清理失败（不影响任务成功）: {exc}",
                project_id=job.project_id,
            )
        cleanup_summary = _release_scan_workspace(job=job)
        job_result_summary["cleanup"] = cleanup_summary
        job.result_summary = dict(job_result_summary)
        _append_scan_log(
            job_id=job.id,
            stage=JobStage.CLEANUP.value,
            message=(
                "扫描工作区清理完成。"
                f" workspace_released={cleanup_summary['workspace_released']}"
            ),
            project_id=job.project_id,
        )
        _set_scan_step_status(
            session,
            job_id=job.id,
            step_key="cleanup",
            status=JobStepStatus.SUCCEEDED.value,
            commit=True,
        )
        job.status = JobStatus.SUCCEEDED.value
        job.failure_code = None
        job.failure_stage = None
        job.failure_category = None
        job.failure_hint = None
        job.finished_at = utc_now()
        try:
            job.result_summary = dict(job_result_summary)
            job_result_summary["archive"] = _write_scan_result_archive(job=job)
        except Exception as exc:
            _append_scan_log(
                job_id=job.id,
                stage=JobStage.CLEANUP.value,
                message=f"扫描结果最终归档刷新失败（不影响任务成功）: {exc}",
                project_id=job.project_id,
            )
        job.result_summary = dict(job_result_summary)
        _append_job_stream_event_safe(
            session,
            job_id=job.id,
            project_id=job.project_id,
            event_type="job_status",
            payload={
                "status": job.status,
                "stage": job.stage,
                "failure_code": job.failure_code,
                "failure_stage": job.failure_stage,
            },
        )
        _finalize_scan_steps(
            session,
            job_id=job.id,
            final_status=JobStatus.SUCCEEDED.value,
            stage=job.stage,
        )
        _append_scan_log(
            job_id=job.id,
            stage=JobStage.CLEANUP.value,
            message=f"任务成功，发现 {execution.result_summary.get('total_findings', 0)} 条结果",
            project_id=job.project_id,
        )
        _append_job_stream_event_safe(
            session,
            job_id=job.id,
            project_id=job.project_id,
            event_type="done",
            payload={
                "status": JobStatus.SUCCEEDED.value,
                "stage": job.stage,
                "total_findings": execution.result_summary.get("total_findings", 0),
            },
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
            if job.status in TERMINAL_SCAN_STATUSES:
                return
            detail_text = _tail_text(
                json.dumps(exc.detail or {}, ensure_ascii=False), max_chars=3000
            )
            _append_scan_log(
                job_id=job.id,
                stage=job.stage,
                message=(
                    f"任务异常收口: code={exc.code}, stage={job.stage}, detail={detail_text}"
                ),
                project_id=job.project_id,
            )
            is_timeout = exc.code in TIMEOUT_FAILURE_CODES or exc.code.endswith(
                "_TIMEOUT"
            )
            final_status = (
                JobStatus.CANCELED.value
                if exc.code == "SCAN_CANCELED"
                else (JobStatus.TIMEOUT.value if is_timeout else JobStatus.FAILED.value)
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
        traceback_text = traceback.format_exc()
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None:
            if job.status in TERMINAL_SCAN_STATUSES:
                return
            _append_scan_log(
                job_id=job.id,
                stage=job.stage,
                message=(
                    "任务异常收口: "
                    f"stage={job.stage}, traceback={_tail_text(traceback_text, max_chars=3000)}"
                ),
                project_id=job.project_id,
            )
            _fail_scan_job(
                session,
                job=job,
                stage=job.stage,
                failure_code="SCAN_INTERNAL_ERROR",
                failure_category=JobFailureCategory.SYSTEM.value,
                request_id=str(job.payload.get("request_id", "")),
                detail={
                    "error": "SCAN_INTERNAL_ERROR",
                    "traceback_tail": _tail_text(traceback_text, max_chars=4000),
                },
            )
    finally:
        if slot_acquired:
            release_scan_runtime_slot(job_id=job_id, db_bind=session.get_bind())
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
    _append_job_stream_event_safe(
        db,
        job_id=job.id,
        project_id=job.project_id,
        event_type="job_status",
        payload={
            "status": job.status,
            "stage": job.stage,
            "failure_code": job.failure_code,
            "failure_stage": job.failure_stage,
        },
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
    result_summary = {**(job.result_summary or {})}
    if detail:
        result_summary["failure_detail"] = detail
        executed_stages = detail.get("executed_stages")
        if isinstance(executed_stages, list):
            result_summary["external_stages"] = executed_stages
        _append_scan_log(
            job_id=job.id,
            stage=stage,
            message=(
                f"失败上下文: {_tail_text(json.dumps(detail, ensure_ascii=False), max_chars=3000)}"
            ),
            project_id=job.project_id,
        )
    try:
        job.result_summary = dict(result_summary)
        job.result_summary["archive"] = _write_scan_result_archive(job=job)
        result_summary["archive"] = job.result_summary.get("archive")
        _set_scan_step_status(
            db,
            job_id=job.id,
            step_key="archive",
            status=JobStepStatus.SUCCEEDED.value,
            commit=True,
        )
    except Exception as exc:
        _append_scan_log(
            job_id=job.id,
            stage=stage,
            message=f"扫描结果归档写入失败（不影响失败收口）: {exc}",
            project_id=job.project_id,
        )
    try:
        result_summary["neo4j_cleanup"] = _cleanup_external_neo4j_database(
            job=job, result_summary=result_summary
        )
    except Exception as exc:
        result_summary["neo4j_cleanup"] = {
            "enabled": True,
            "database": None,
            "cleanup_attempted": True,
            "cleanup_succeeded": False,
            "cleanup_skipped_reason": None,
            "error": str(exc),
        }
        _append_scan_log(
            job_id=job.id,
            stage=stage,
            message=f"Neo4j 清理失败（不影响失败收口）: {exc}",
            project_id=job.project_id,
        )
    cleanup_summary = _release_scan_workspace(job=job)
    result_summary["cleanup"] = cleanup_summary
    job.result_summary = dict(result_summary)
    _finalize_scan_steps(
        db,
        job_id=job.id,
        final_status=final_status,
        failure_code=failure_code,
        stage=stage,
    )
    failure_label = (
        "任务超时" if final_status == JobStatus.TIMEOUT.value else "任务失败"
    )
    _append_scan_log(
        job_id=job.id,
        stage=stage,
        message=(
            f"{failure_label}: code={failure_code}, category={failure_category}, "
            f"workspace_released={cleanup_summary['workspace_released']}"
        ),
        project_id=job.project_id,
    )
    _append_job_stream_event_safe(
        db,
        job_id=job.id,
        project_id=job.project_id,
        event_type="done",
        payload={
            "status": final_status,
            "stage": stage,
            "failure_code": failure_code,
        },
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
    resolved_rule_keys = normalize_rule_keys(
        list(job.payload.get("resolved_rule_keys") or [])
    )
    direct_rule_keys = normalize_rule_keys(list(job.payload.get("rule_keys") or []))
    rule_keys = resolved_rule_keys or direct_rule_keys
    _append_scan_log(
        job_id=job.id,
        stage=JobStage.QUERY.value,
        message=f"stub 执行: rule_count={len(rule_keys)}",
    )

    findings: list[dict[str, str]] = []
    stub_location = _build_stub_location(version_id=job.version_id)
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
            _build_stub_finding(
                rule_key=rule_key,
                severity=severities[idx % len(severities)],
                location=stub_location,
                index=idx,
            )
        )

    result_summary = _build_result_summary(
        findings=findings,
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


def _run_external_scan(*, job: Job, db: Session) -> ScanExecutionResult:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    live_findings: list[dict[str, object]] = []
    seen_canonical_fingerprints: set[str] = set()
    live_severity_counts = {
        FindingSeverity.HIGH.value: 0,
        FindingSeverity.MED.value: 0,
        FindingSeverity.LOW.value: 0,
    }

    stage_by_step = {
        "joern": JobStage.ANALYZE.value,
        "neo4j_import": JobStage.ANALYZE.value,
        "post_labels": JobStage.QUERY.value,
        "source_semantic": JobStage.QUERY.value,
        "rules": JobStage.QUERY.value,
    }

    def _on_live_rule_finding(raw_finding: dict[str, object]) -> None:
        persisted = _persist_external_finding_live(
            job=job,
            db_bind=db.get_bind(),
            raw_finding=raw_finding,
            seen_fingerprints=seen_canonical_fingerprints,
        )
        if persisted is None:
            return
        finding_payload = persisted.get("finding")
        if isinstance(finding_payload, dict):
            severity = str(finding_payload.get("severity") or "").strip().upper()
            finding_snapshot = {**dict(raw_finding), **dict(finding_payload)}
            live_findings.append(finding_snapshot)
            if severity in live_severity_counts:
                live_severity_counts[severity] += 1
            summary_payload = {
                "total_findings": len(live_findings),
                "severity_counts": dict(live_severity_counts),
            }
            live_session_factory = sessionmaker(
                bind=db.get_bind(),
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
            with live_session_factory() as live_db:
                append_job_stream_event(
                    live_db,
                    job_id=job.id,
                    project_id=job.project_id,
                    event_type="summary_update",
                    payload=summary_payload,
                )
                live_db.commit()

    def _on_external_stage_status(step_key: str, status: str) -> None:
        stage = stage_by_step.get(step_key)
        if stage and job.stage != stage and status == JobStepStatus.RUNNING.value:
            _set_scan_job_running(db, job=job, stage=stage)
        _set_scan_step_status(
            db,
            job_id=job.id,
            step_key=step_key,
            status=status,
            commit=True,
        )

    external_result = run_external_scan_pipeline(
        job=job,
        settings=settings,
        backend_root=backend_root,
        append_log=lambda stage, message: _append_scan_log(
            job_id=job.id, stage=stage, message=message
        ),
        severity_from_rule_key=_severity_from_rule_key,
        on_stage_status=_on_external_stage_status,
        on_rule_finding=_on_live_rule_finding,
    )
    final_findings = _load_job_finding_snapshots(db, job_id=job.id)
    effective_findings = final_findings or live_findings or external_result.findings

    result_summary = _build_result_summary(
        findings=effective_findings,
        engine_mode="external",
        extra=external_result.summary_extra,
    )
    _append_scan_log(
        job_id=job.id,
        stage=JobStage.AGGREGATE.value,
        message=(
            f"external 结果汇总完成: findings={len(effective_findings)}, "
            f"hit_rules={result_summary.get('hit_rules', 0)}"
        ),
    )
    return ScanExecutionResult(
        findings=effective_findings,
        result_summary=result_summary,
    )


def _build_result_summary(
    *,
    findings: list[dict[str, object]],
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
        severity = str(item.get("severity") or "")
        if severity in severity_counts:
            severity_counts[severity] += 1
        rule_key = str(item.get("rule_key") or "").strip()
        if rule_key:
            hit_rules.add(rule_key)

    summary: dict[str, object] = {
        "engine_mode": engine_mode,
        "total_findings": len(findings),
        "severity_counts": severity_counts,
        "hit_rule_count": len(hit_rules),
        "partial_failures": [],
    }
    if extra:
        summary.update(extra)
    return summary


def _create_finding_model_from_draft(*, job: Job, draft: dict[str, object]) -> Finding:
    source = draft["source"] if isinstance(draft.get("source"), dict) else {}
    sink = draft["sink"] if isinstance(draft.get("sink"), dict) else {}
    evidence_payload = _normalize_evidence_payload(draft.get("evidence"))
    if draft.get("trace_summary"):
        evidence_payload.setdefault("trace_summary", draft.get("trace_summary"))
    if isinstance(draft.get("code_context"), dict):
        evidence_payload.setdefault("code_context", draft.get("code_context"))
    return Finding(
        project_id=job.project_id,
        version_id=job.version_id,
        job_id=job.id,
        rule_key=str(draft["rule_key"]),
        rule_version=_to_int(draft.get("rule_version")),
        vuln_type=str(draft["vuln_type"]) if draft.get("vuln_type") else None,
        severity=str(draft["severity"]),
        status=FindingStatus.OPEN.value,
        file_path=str(draft["file_path"]) if draft.get("file_path") else None,
        line_start=_to_int(draft.get("line_start")),
        line_end=_to_int(draft.get("line_end")),
        has_path=bool(draft.get("has_path", False)),
        path_length=_to_int(draft.get("path_length")),
        source_file=str(source["file"])
        if isinstance(source.get("file"), str)
        else None,
        source_line=_to_int(source.get("line")),
        sink_file=str(sink["file"]) if isinstance(sink.get("file"), str) else None,
        sink_line=_to_int(sink.get("line")),
        evidence_json=evidence_payload,
    )


def _normalize_finding_path_graph(
    *, version_id: uuid.UUID, path_item: dict[str, object], path_index: int
) -> dict[str, object] | None:
    return normalize_path_graph(
        version_id=version_id,
        path_item=path_item,
        path_index=path_index,
    )


def _normalize_external_finding_payload(
    *, version_id: uuid.UUID, raw_finding: dict[str, object]
) -> dict[str, object]:
    return normalize_external_finding_candidate(
        version_id=version_id,
        raw_finding=raw_finding,
    )


def _refine_external_finding_paths_with_runtime(
    *,
    job: Job,
    finding_payload: dict[str, object],
) -> dict[str, object]:
    return repair_external_finding_candidate(
        job=job,
        finding_payload=finding_payload,
    )


def _persist_finding_paths(
    db: Session,
    *,
    version_id: uuid.UUID,
    finding: Finding,
    paths: list[dict[str, object]],
) -> int:
    saved_count = 0
    for path_index, path_item in enumerate(paths):
        if not isinstance(path_item, dict):
            continue
        normalized_path = _normalize_finding_path_graph(
            version_id=version_id,
            path_item=path_item,
            path_index=path_index,
        )
        if normalized_path is None:
            continue
        nodes = normalized_path["nodes"]
        steps = normalized_path["steps"]
        edges = normalized_path["edges"]
        path_model = FindingPath(
            finding_id=finding.id,
            path_order=path_index,
            path_length=max(
                0,
                _to_int(
                    normalized_path.get("path_length"),
                    default=len(edges) or (len(steps) - 1),
                )
                or len(edges)
                or (len(steps) - 1),
            ),
        )
        db.add(path_model)
        db.flush()
        for node_index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            db.add(
                FindingPathStep(
                    finding_path_id=path_model.id,
                    step_order=node_index,
                    labels_json=[
                        str(item)
                        for item in node.get("labels") or []
                        if isinstance(item, str) and item.strip()
                    ],
                    file_path=str(node.get("file") or "").strip() or None,
                    line_no=_to_int(node.get("line")),
                    column_no=_to_int(node.get("column")),
                    func_name=str(node.get("func_name") or "").strip() or None,
                    display_name=str(node.get("display_name") or "").strip() or None,
                    symbol_name=str(node.get("symbol_name") or "").strip() or None,
                    owner_method=str(node.get("owner_method") or "").strip() or None,
                    type_name=str(node.get("type_name") or "").strip() or None,
                    node_kind=str(node.get("node_kind") or "").strip() or None,
                    code_snippet=(str(node.get("code_snippet") or "").strip() or None),
                    node_ref=str(node.get("node_ref") or f"step-{node_index}"),
                    raw_props_json=(
                        dict(node.get("raw_props"))
                        if isinstance(node.get("raw_props"), dict)
                        else {}
                    ),
                )
            )
        for edge_index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            db.add(
                FindingPathEdge(
                    finding_path_id=path_model.id,
                    edge_order=edge_index,
                    from_step_order=_to_int(edge.get("from_step_id")),
                    to_step_order=_to_int(edge.get("to_step_id")),
                    edge_type=str(edge.get("edge_type") or "STEP_NEXT"),
                    label=str(edge.get("label") or "").strip() or None,
                    is_hidden=bool(edge.get("is_hidden", False)),
                    props_json=(
                        dict(edge.get("props_json"))
                        if isinstance(edge.get("props_json"), dict)
                        else {}
                    ),
                )
            )
        saved_count += 1
    return saved_count


def _persist_external_finding_live(
    *,
    job: Job,
    db_bind: Any,
    raw_finding: dict[str, object],
    seen_fingerprints: set[str] | None = None,
) -> dict[str, object] | None:
    raw_rule_key = str(raw_finding.get("rule_key") or "").strip()
    if not raw_rule_key:
        return None
    normalized_finding = process_external_finding_candidate(
        job=job,
        raw_finding=raw_finding,
        seen_fingerprints=seen_fingerprints,
    )
    if normalized_finding is None:
        return None
    normalized_evidence = _normalize_evidence_payload(
        normalized_finding.get("evidence") or normalized_finding.get("evidence_json")
    )
    repair_status = str(normalized_evidence.get("repair_status") or "").strip()
    raw_has_path = bool(raw_finding.get("has_path")) or bool(raw_finding.get("paths"))
    if repair_status == "downgraded_no_path" and raw_has_path:
        return None
    try:
        normalized_rule_key = normalize_rule_selector(raw_rule_key)
    except AppError:
        normalized_rule_key = raw_rule_key
    rule_meta = get_rules_by_keys({normalized_rule_key})
    drafts = _normalize_finding_drafts(
        findings=[normalized_finding],
        rule_meta_by_key=rule_meta,
    )
    if not drafts:
        return None
    draft = _attach_code_contexts(job=job, finding_drafts=[drafts[0]])[0]
    paths = (
        normalized_finding.get("paths")
        if isinstance(normalized_finding.get("paths"), list)
        else []
    )
    evidence_payload = normalized_evidence
    coarse_dedupe_key = (
        str(evidence_payload.get("coarse_dedupe_key") or "").strip() or None
    )
    current_dedupe_score = _to_int(evidence_payload.get("dedupe_score"), default=0) or 0

    live_session_factory = sessionmaker(
        bind=db_bind,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    with live_session_factory() as live_db:
        live_job = live_db.get(Job, job.id)
        if live_job is None:
            return None
        if coarse_dedupe_key:
            existing_rows = live_db.scalars(
                select(Finding).where(
                    Finding.job_id == live_job.id,
                    Finding.rule_key == str(draft.get("rule_key") or "").strip(),
                    Finding.source_file
                    == (str(draft.get("source", {}).get("file") or "").strip() or None),
                    Finding.source_line == _to_int(draft.get("source", {}).get("line")),
                )
            ).all()
            duplicate_ids_to_delete: list[uuid.UUID] = []
            for existing in existing_rows:
                existing_evidence = _normalize_evidence_payload(existing.evidence_json)
                existing_key = (
                    str(existing_evidence.get("coarse_dedupe_key") or "").strip()
                    or None
                )
                if existing_key != coarse_dedupe_key:
                    continue
                existing_score = (
                    _to_int(existing_evidence.get("dedupe_score"), default=0) or 0
                )
                if existing_score >= current_dedupe_score:
                    return None
                duplicate_ids_to_delete.append(existing.id)
            if duplicate_ids_to_delete:
                live_db.execute(
                    delete(Finding).where(Finding.id.in_(duplicate_ids_to_delete))
                )
                live_db.flush()
        finding = _create_finding_model_from_draft(job=live_job, draft=draft)
        live_db.add(finding)
        live_db.flush()
        saved_paths = _persist_finding_paths(
            live_db,
            version_id=live_job.version_id,
            finding=finding,
            paths=paths,
        )
        payload = {
            "finding": _serialize_finding_record(finding),
            "paths": paths,
            "saved_path_count": saved_paths,
        }
        append_job_stream_event(
            live_db,
            job_id=live_job.id,
            project_id=live_job.project_id,
            event_type="finding_upsert",
            payload=payload,
        )
        live_db.commit()
        return payload


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


def _normalize_finding_drafts(
    *,
    findings: list[dict[str, str]],
    rule_meta_by_key: dict[str, Any],
) -> list[dict[str, object]]:
    drafts: list[dict[str, object]] = []
    for finding_data in findings:
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

        source_line = _to_int(finding_data.get("source_line"))
        sink_line = _to_int(finding_data.get("sink_line"))
        line_start = _to_int(finding_data.get("line_start"))
        line_end = _to_int(finding_data.get("line_end"), default=line_start)

        evidence = _normalize_evidence_payload(
            finding_data.get("evidence") or finding_data.get("evidence_json")
        )
        draft: dict[str, object] = {
            "rule_key": rule_key,
            "rule_version": _to_int(
                finding_data.get("rule_version"),
                default=meta.active_version if meta is not None else None,
            ),
            "vuln_type": (
                str(finding_data.get("vuln_type") or "").strip()
                or (meta.vuln_type if meta is not None else None)
            ),
            "severity": str(finding_data.get("severity") or FindingSeverity.MED.value),
            "file_path": fallback_path,
            "line_start": line_start,
            "line_end": line_end,
            "source": {"file": source_file, "line": source_line},
            "sink": {"file": sink_file, "line": sink_line},
            "evidence": evidence,
            "trace_summary": _build_trace_summary(
                rule_key=rule_key,
                file_path=fallback_path,
                line_start=line_start,
                line_end=line_end,
                source_file=source_file,
                source_line=source_line,
                sink_file=sink_file,
                sink_line=sink_line,
            ),
            "has_path": bool(finding_data.get("has_path", False)),
            "path_length": _to_int(finding_data.get("path_length")),
        }
        if _is_valid_finding_draft(draft):
            drafts.append(draft)
    return drafts


def _attach_code_contexts(
    *,
    job: Job,
    finding_drafts: list[dict[str, object]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for draft in finding_drafts:
        copied = dict(draft)
        code_context = _build_code_context(version_id=job.version_id, draft=draft)
        if code_context:
            copied["code_context"] = code_context
        enriched.append(copied)
    return enriched


def _is_valid_finding_draft(draft: dict[str, object]) -> bool:
    for key in FINDING_DRAFT_REQUIRED_KEYS:
        if key not in draft:
            return False
    rule_key = draft.get("rule_key")
    if not isinstance(rule_key, str) or not rule_key.strip():
        return False
    severity = str(draft.get("severity") or "").strip().upper()
    if severity not in {item.value for item in FindingSeverity}:
        return False
    return True


def _build_trace_summary(
    *,
    rule_key: str,
    file_path: str | None,
    line_start: int | None,
    line_end: int | None,
    source_file: str | None,
    source_line: int | None,
    sink_file: str | None,
    sink_line: int | None,
) -> str:
    location = "-"
    if file_path:
        if line_start is not None:
            if line_end is not None and line_end != line_start:
                location = f"{file_path}:{line_start}-{line_end}"
            else:
                location = f"{file_path}:{line_start}"
        else:
            location = file_path
    source = _format_location(source_file, source_line)
    sink = _format_location(sink_file, sink_line)
    return f"rule={rule_key}; location={location}; source={source}; sink={sink}"


def _format_location(file_path: str | None, line: int | None) -> str:
    if not file_path:
        return "-"
    if line is None:
        return file_path
    return f"{file_path}:{line}"


def _build_code_context(
    *,
    version_id: uuid.UUID,
    draft: dict[str, object],
) -> dict[str, dict[str, object]]:
    code_context: dict[str, dict[str, object]] = {}
    focus = _read_snapshot_snippet(
        version_id=version_id,
        file_path=str(draft.get("file_path") or "").strip(),
        line_start=_to_int(draft.get("line_start")),
        line_end=_to_int(draft.get("line_end")),
        before=2,
        after=2,
    )
    if focus:
        code_context["focus"] = focus

    source = draft.get("source") if isinstance(draft.get("source"), dict) else {}
    source_context = _read_snapshot_snippet(
        version_id=version_id,
        file_path=str(source.get("file") or "").strip(),
        line_start=_to_int(source.get("line")),
        line_end=_to_int(source.get("line")),
        before=2,
        after=2,
    )
    if source_context and source_context != focus:
        code_context["source"] = source_context

    sink = draft.get("sink") if isinstance(draft.get("sink"), dict) else {}
    sink_context = _read_snapshot_snippet(
        version_id=version_id,
        file_path=str(sink.get("file") or "").strip(),
        line_start=_to_int(sink.get("line")),
        line_end=_to_int(sink.get("line")),
        before=2,
        after=2,
    )
    if sink_context and sink_context != focus and sink_context != source_context:
        code_context["sink"] = sink_context
    return code_context


def _read_snapshot_snippet(
    *,
    version_id: uuid.UUID,
    file_path: str,
    line_start: int | None,
    line_end: int | None,
    before: int,
    after: int,
) -> dict[str, object] | None:
    if not file_path or line_start is None or line_start <= 0:
        return None
    resolved_path = _resolve_snapshot_relative_path(
        version_id=version_id, raw_path=file_path
    )
    if not resolved_path:
        return None
    extra_after = max(0, min(8, (line_end or line_start) - line_start))
    try:
        lines, start_line, end_line = read_snapshot_file_context(
            version_id=version_id,
            path=resolved_path,
            line=line_start,
            before=before,
            after=after + extra_after,
        )
    except AppError:
        return None
    return {
        "file_path": resolved_path,
        "start_line": start_line,
        "end_line": end_line,
        "snippet": _format_code_snippet(lines, start_line),
    }


def _snapshot_source_root(*, version_id: uuid.UUID) -> Path:
    return (
        _absolute_settings_path(get_settings().snapshot_storage_root)
        / str(version_id)
        / "source"
    )


def _resolve_snapshot_relative_path(
    *, version_id: uuid.UUID, raw_path: str
) -> str | None:
    normalized = raw_path.replace("\\", "/").strip()
    if not normalized:
        return None
    source_root = _snapshot_source_root(version_id=version_id)
    if not source_root.exists() or not source_root.is_dir():
        return None

    candidates = _candidate_snapshot_paths(normalized)
    source_root_resolved = source_root.resolve()
    for candidate in candidates:
        resolved = (source_root / candidate).resolve()
        if resolved.exists() and resolved.is_file():
            try:
                return resolved.relative_to(source_root_resolved).as_posix()
            except ValueError:
                continue

    target_name = Path(candidates[0]).name if candidates else Path(normalized).name
    for entry in source_root.rglob(target_name):
        if not entry.is_file():
            continue
        relative = entry.relative_to(source_root).as_posix()
        for candidate in candidates:
            if relative.endswith(candidate) or candidate.endswith(relative):
                return relative
    return None


def _candidate_snapshot_paths(raw_path: str) -> list[str]:
    normalized = raw_path.replace("\\", "/").strip()
    if not normalized:
        return []
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    candidates: list[str] = []
    for candidate in (normalized, _strip_source_prefix(normalized)):
        cleaned = candidate.strip().lstrip("/")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    return candidates


def _strip_source_prefix(value: str) -> str:
    lowered = value.lower()
    marker = "/source/"
    index = lowered.rfind(marker)
    if index >= 0:
        return value[index + len(marker) :]
    if lowered.startswith("source/"):
        return value[len("source/") :]
    return value


def _format_code_snippet(lines: list[str], start_line: int) -> str:
    return "\n".join(
        f"{start_line + index}: {line}" for index, line in enumerate(lines)
    )


def _build_stub_location(*, version_id: uuid.UUID) -> dict[str, object] | None:
    source_root = _snapshot_source_root(version_id=version_id)
    if not source_root.exists() or not source_root.is_dir():
        return None
    for candidate in sorted(
        source_root.rglob("*"), key=lambda item: item.as_posix().lower()
    ):
        if not candidate.is_file():
            continue
        try:
            lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        relative_path = candidate.relative_to(source_root).as_posix()
        total_lines = max(1, len(lines))
        source_line = 1 if total_lines >= 1 else None
        sink_line = min(total_lines, 3)
        return {
            "file_path": relative_path,
            "line_start": source_line,
            "line_end": min(total_lines, max(1, sink_line)),
            "source_file": relative_path,
            "source_line": source_line,
            "sink_file": relative_path,
            "sink_line": sink_line,
        }
    return None


def _build_stub_finding(
    *,
    rule_key: str,
    severity: str,
    location: dict[str, object] | None,
    index: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "rule_key": rule_key,
        "severity": severity,
        "evidence": {"stub": True, "ordinal": index + 1},
    }
    if location:
        payload.update(location)
        payload["evidence"] = {
            "stub": True,
            "ordinal": index + 1,
            "location": f"{location.get('file_path')}:{location.get('line_start')}",
        }
    return payload


def _attach_ai_payloads(
    finding_drafts: list[dict[str, object]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for draft in finding_drafts:
        copied = dict(draft)
        llm_payload = _build_llm_payload(draft)
        copied["llm_payload"] = llm_payload
        copied["llm_prompt_block"] = _build_llm_prompt_block(llm_payload)
        enriched.append(copied)
    return enriched


def _build_llm_payload(draft: dict[str, object]) -> dict[str, object]:
    source = draft["source"] if isinstance(draft.get("source"), dict) else {}
    sink = draft["sink"] if isinstance(draft.get("sink"), dict) else {}
    evidence = _normalize_evidence_payload(draft.get("evidence"))
    evidence_preview = _build_evidence_preview(evidence)
    code_context = _build_llm_code_context(draft.get("code_context"))
    return {
        "rule_key": _truncate_text(
            str(draft.get("rule_key") or ""), LLM_TEXT_MAX_LENGTH
        ),
        "severity": _truncate_text(str(draft.get("severity") or ""), 32),
        "vuln_type": _truncate_text(str(draft.get("vuln_type") or ""), 64),
        "location": {
            "file_path": _truncate_text(
                str(draft.get("file_path") or ""), LLM_TEXT_MAX_LENGTH
            ),
            "line_start": _to_int(draft.get("line_start")),
            "line_end": _to_int(draft.get("line_end")),
        },
        "source": {
            "file": _truncate_text(str(source.get("file") or ""), LLM_TEXT_MAX_LENGTH),
            "line": _to_int(source.get("line")),
        },
        "sink": {
            "file": _truncate_text(str(sink.get("file") or ""), LLM_TEXT_MAX_LENGTH),
            "line": _to_int(sink.get("line")),
        },
        "trace_summary": _truncate_text(
            str(draft.get("trace_summary") or ""), LLM_TEXT_MAX_LENGTH
        ),
        "why_flagged": _truncate_text(
            _build_reason_summary(draft),
            LLM_TEXT_MAX_LENGTH,
        ),
        "evidence_preview": evidence_preview,
        "code_context": code_context,
    }


def _build_evidence_preview(evidence: dict[str, object]) -> list[str]:
    preview: list[str] = []
    for key, value in evidence.items():
        if len(preview) >= LLM_EVIDENCE_ITEMS_MAX_COUNT:
            break
        if isinstance(value, list):
            for item in value:
                if len(preview) >= LLM_EVIDENCE_ITEMS_MAX_COUNT:
                    break
                preview.append(
                    _truncate_text(f"{key}={item}", LLM_EVIDENCE_ITEM_MAX_LENGTH)
                )
            continue
        preview.append(_truncate_text(f"{key}={value}", LLM_EVIDENCE_ITEM_MAX_LENGTH))
    return preview


def _build_llm_prompt_block(llm_payload: dict[str, object]) -> str:
    location = llm_payload.get("location")
    source = llm_payload.get("source")
    sink = llm_payload.get("sink")
    evidence_preview = llm_payload.get("evidence_preview")
    code_context = llm_payload.get("code_context")
    location_text = "-"
    if isinstance(location, dict):
        file_path = str(location.get("file_path") or "").strip()
        line_start = _to_int(location.get("line_start"))
        line_end = _to_int(location.get("line_end"))
        if file_path:
            if line_start is not None and line_end is not None:
                location_text = f"{file_path}:{line_start}-{line_end}"
            elif line_start is not None:
                location_text = f"{file_path}:{line_start}"
            else:
                location_text = file_path
    source_text = "-"
    if isinstance(source, dict):
        source_text = _format_location(
            str(source.get("file") or "").strip() or None,
            _to_int(source.get("line")),
        )
    sink_text = "-"
    if isinstance(sink, dict):
        sink_text = _format_location(
            str(sink.get("file") or "").strip() or None,
            _to_int(sink.get("line")),
        )
    lines = [
        f"Rule: {llm_payload.get('rule_key')}",
        f"Severity: {llm_payload.get('severity')}",
        f"VulnType: {llm_payload.get('vuln_type') or '-'}",
        f"Location: {location_text}",
        f"Reason: {llm_payload.get('why_flagged') or '-'}",
        f"Source: {source_text}",
        f"Sink: {sink_text}",
        f"Trace: {llm_payload.get('trace_summary') or '-'}",
    ]
    if isinstance(evidence_preview, list) and evidence_preview:
        lines.append("Evidence:")
        lines.extend(f"- {item}" for item in evidence_preview if str(item).strip())
    if isinstance(code_context, dict):
        context_lines = _build_llm_context_lines(code_context)
        if context_lines:
            lines.append("Code:")
            lines.extend(context_lines)
    return _truncate_text("\n".join(lines), LLM_TEXT_MAX_LENGTH * 2)


def _build_reason_summary(draft: dict[str, object]) -> str:
    vuln_type = str(draft.get("vuln_type") or "").strip()
    source = draft.get("source") if isinstance(draft.get("source"), dict) else {}
    sink = draft.get("sink") if isinstance(draft.get("sink"), dict) else {}
    source_text = _format_location(
        str(source.get("file") or "").strip() or None,
        _to_int(source.get("line")),
    )
    sink_text = _format_location(
        str(sink.get("file") or "").strip() or None,
        _to_int(sink.get("line")),
    )
    if source_text != "-" and sink_text != "-":
        return f"{vuln_type or '风险'} 从 {source_text} 传播到 {sink_text}。"
    location = _format_location(
        str(draft.get("file_path") or "").strip() or None,
        _to_int(draft.get("line_start")),
    )
    return f"规则 {draft.get('rule_key')} 在 {location} 命中。"


def _build_llm_code_context(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    payload: dict[str, str] = {}
    for key in ("focus", "source", "sink"):
        entry = value.get(key)
        if not isinstance(entry, dict):
            continue
        snippet = str(entry.get("snippet") or "").strip()
        if not snippet:
            continue
        payload[key] = _truncate_text(snippet, LLM_CODE_SNIPPET_MAX_LENGTH)
    return payload


def _build_llm_context_lines(code_context: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for key, label in (("focus", "Focus"), ("source", "Source"), ("sink", "Sink")):
        snippet = str(code_context.get(key) or "").strip()
        if not snippet:
            continue
        lines.append(f"- {label}:")
        lines.append(snippet)
    return lines


def _truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max(0, max_length - 1)] + "…"


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
