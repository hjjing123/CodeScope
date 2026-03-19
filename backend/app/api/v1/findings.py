from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_principal,
    require_project_action,
    require_project_resource_action,
)
from app.models import (
    Finding,
    FindingLabel,
    FindingSeverity,
    FindingStatus,
    Job,
    JobStatus,
    JobType,
    Project,
    SystemRole,
    UserProjectRole,
    Version,
)
from app.schemas.finding import (
    FindingLabelActionPayload,
    FindingLabelPayload,
    FindingLabelRequest,
    FindingListPayload,
    FindingPathEdgePayload,
    FindingPathListPayload,
    FindingPathNodePayload,
    FindingPathNodeContextPayload,
    FindingPathPayload,
    FindingPathStepPayload,
    FindingPayload,
    ProjectResultOverviewPayload,
    ScanResultListPayload,
    ScanResultRowPayload,
)
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.authorization_service import (
    ensure_project_action,
    ensure_resource_action,
)
from app.services.ai_service import (
    build_finding_ai_review_summary,
    map_latest_finding_ai_assessments,
)
from app.services.finding_presentation_service import build_finding_presentation
from app.services.finding_path_service import (
    load_finding_path_context,
    query_finding_paths,
)
from app.services.source_location_service import normalize_graph_location


router = APIRouter(tags=["findings"])


def _validate_severity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    allowed = {item.value for item in FindingSeverity}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="severity 值不合法",
            detail={"allowed_severities": sorted(allowed)},
        )
    return normalized


def _validate_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    allowed = {item.value for item in FindingStatus}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="status 值不合法",
            detail={"allowed_statuses": sorted(allowed)},
        )
    return normalized


def _validate_scan_job_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    allowed = {item.value for item in JobStatus}
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="scan result status 值不合法",
            detail={"allowed_statuses": sorted(allowed)},
        )
    return normalized


def _validate_sort_by(value: str | None) -> str:
    normalized = (value or "created_at").strip().lower()
    if normalized not in {"severity", "created_at", "path_length"}:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="sort_by 参数不合法",
            detail={"allowed_sort_by": ["severity", "created_at", "path_length"]},
        )
    return normalized


def _validate_sort_order(value: str | None) -> str:
    normalized = (value or "desc").strip().lower()
    if normalized not in {"asc", "desc"}:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="sort_order 参数不合法",
            detail={"allowed_sort_order": ["asc", "desc"]},
        )
    return normalized


def _validate_label_status(value: str) -> str:
    normalized = value.strip().upper()
    allowed = {
        FindingStatus.TP.value,
        FindingStatus.FP.value,
        FindingStatus.NEEDS_REVIEW.value,
    }
    if normalized not in allowed:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="标注状态不合法",
            detail={"allowed_statuses": sorted(allowed)},
        )
    return normalized


def _normalize_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _finding_payload(item: Finding, *, latest_assessment=None) -> FindingPayload:
    file_path, line_start = normalize_graph_location(
        version_id=item.version_id,
        file_path=item.file_path,
        line=item.line_start,
        infer_line=False,
    )
    source_file, source_line = normalize_graph_location(
        version_id=item.version_id,
        file_path=item.source_file,
        line=item.source_line,
        infer_line=False,
    )
    sink_file, sink_line = normalize_graph_location(
        version_id=item.version_id,
        file_path=item.sink_file,
        line=item.sink_line,
        infer_line=False,
    )
    presentation = build_finding_presentation(
        version_id=item.version_id,
        rule_key=item.rule_key,
        vuln_type=item.vuln_type,
        source_file=source_file,
        source_line=source_line,
        file_path=file_path,
        line_start=line_start,
    )
    return FindingPayload(
        id=item.id,
        project_id=item.project_id,
        version_id=item.version_id,
        job_id=item.job_id,
        rule_key=item.rule_key,
        rule_version=item.rule_version,
        vuln_type=item.vuln_type,
        vuln_display_name=presentation.get("vuln_display_name"),
        severity=item.severity,
        status=item.status,
        file_path=file_path,
        line_start=line_start,
        line_end=line_start,
        entry_display=presentation.get("entry_display"),
        entry_kind=presentation.get("entry_kind"),
        has_path=item.has_path,
        path_length=item.path_length,
        source_file=source_file,
        source_line=source_line,
        sink_file=sink_file,
        sink_line=sink_line,
        evidence_json=item.evidence_json,
        ai_review=build_finding_ai_review_summary(latest_assessment),
        created_at=item.created_at,
    )


def _finding_dedupe_key(item: FindingPayload) -> tuple[str, str, str] | None:
    if item.entry_kind != "route":
        return None
    vuln_name = (
        item.vuln_display_name or item.vuln_type or item.rule_key or ""
    ).strip()
    entry_display = (item.entry_display or "").strip()
    if not vuln_name or not entry_display:
        return None
    return (item.rule_key.lower(), vuln_name.lower(), entry_display.lower())


def _finding_dedupe_rank(item: FindingPayload) -> tuple[int, int, int, str]:
    evidence = item.evidence_json if isinstance(item.evidence_json, dict) else {}
    dedupe_score = int(evidence.get("dedupe_score") or 0)
    path_length = int(item.path_length or 0)
    return (
        dedupe_score,
        1 if item.has_path else 0,
        path_length,
        item.created_at.isoformat(),
    )


def _dedupe_finding_payloads(items: list[FindingPayload]) -> list[FindingPayload]:
    selected_by_key: dict[tuple[str, str, str], FindingPayload] = {}
    passthrough: list[FindingPayload] = []
    for item in items:
        dedupe_key = _finding_dedupe_key(item)
        if dedupe_key is None:
            passthrough.append(item)
            continue
        existing = selected_by_key.get(dedupe_key)
        if existing is None or _finding_dedupe_rank(item) > _finding_dedupe_rank(
            existing
        ):
            selected_by_key[dedupe_key] = item
    return passthrough + list(selected_by_key.values())


def _scan_result_row_payload(
    *,
    scan_job: Job,
    project: Project,
    version: Version,
    ai_latest_status: str | None,
) -> ScanResultRowPayload:
    payload = scan_job.payload if isinstance(scan_job.payload, dict) else {}
    ai_payload = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
    result_summary = (
        scan_job.result_summary if isinstance(scan_job.result_summary, dict) else {}
    )
    resolved_rule_keys = payload.get("resolved_rule_keys")
    rule_count = len(resolved_rule_keys) if isinstance(resolved_rule_keys, list) else 0
    severity_dist = (
        result_summary.get("severity_counts")
        if isinstance(result_summary.get("severity_counts"), dict)
        else {}
    )
    return ScanResultRowPayload(
        scan_job_id=scan_job.id,
        project_id=project.id,
        project_name=project.name,
        version_id=version.id,
        version_name=version.name,
        job_status=scan_job.status,
        result_generated_at=scan_job.finished_at
        or scan_job.updated_at
        or scan_job.created_at,
        created_at=scan_job.created_at,
        finished_at=scan_job.finished_at,
        created_by=scan_job.created_by,
        rule_count=rule_count,
        total_findings=int(result_summary.get("total_findings") or 0),
        severity_dist={
            key: int(value or 0)
            for key, value in severity_dist.items()
            if isinstance(key, str)
        },
        ai_enabled=bool(ai_payload.get("enabled")),
        ai_latest_status=ai_latest_status,
    )


def _map_latest_ai_status_by_scan_job(
    db: Session, *, scan_job_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    normalized_ids = [item for item in scan_job_ids if isinstance(item, uuid.UUID)]
    if not normalized_ids:
        return {}
    target_ids = {str(item) for item in normalized_ids}
    ai_jobs = db.scalars(
        select(Job)
        .where(Job.job_type == JobType.AI.value)
        .order_by(Job.created_at.desc())
    ).all()
    latest_by_scan_job: dict[uuid.UUID, str] = {}
    for job in ai_jobs:
        payload = job.payload if isinstance(job.payload, dict) else {}
        scan_job_id = str(payload.get("scan_job_id") or "").strip()
        if not scan_job_id or scan_job_id not in target_ids:
            continue
        try:
            parsed_scan_job_id = uuid.UUID(scan_job_id)
        except ValueError:
            continue
        if parsed_scan_job_id not in latest_by_scan_job:
            latest_by_scan_job[parsed_scan_job_id] = job.status
    return latest_by_scan_job


def _validate_finding_scope(
    db: Session,
    *,
    project_id: uuid.UUID | None,
    version_id: uuid.UUID | None,
    job_id: uuid.UUID | None,
) -> tuple[Version | None, Job | None]:
    version: Version | None = None
    job: Job | None = None

    if version_id is not None:
        version = db.get(Version, version_id)
        if version is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="版本不存在")
        if project_id is not None and version.project_id != project_id:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="version_id 不属于当前项目",
            )

    if job_id is not None:
        job = db.get(Job, job_id)
        if job is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
        if job.job_type != JobType.SCAN.value:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="job_id 必须是扫描任务",
            )
        if project_id is not None and job.project_id != project_id:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="job_id 不属于当前项目",
            )
        if version is not None and job.version_id != version.id:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="job_id 不属于当前版本",
            )

    return version, job


CONFIG_EXTENSIONS = {'.xml', '.properties', '.yaml', '.yml', '.json', '.conf', '.ini', '.toml'}

def _sort_finding_payloads(
    items: list[FindingPayload], *, sort_by: str, sort_order: str
) -> list[FindingPayload]:
    reverse = sort_order == "desc"
    
    # Define rank: Config(2) > Code(1) > Route(0) (Descending Order)
    # Config: ends with CONFIG_EXTENSIONS
    # Route: entry_kind == "route"
    # Code: Everything else (e.g. .java, .py)
    
    def get_type_rank(item: FindingPayload) -> int:
        is_route = (item.entry_kind == "route")
        if is_route:
            val = 0
        else:
            # Check if config file
            fpath = (item.file_path or "").lower()
            is_config = any(fpath.endswith(ext) for ext in CONFIG_EXTENSIONS)
            val = 2 if is_config else 1
            
        if not reverse: # Ascending: Route(2) > Code(1) > Config(0) -> effectively Config < Code < Route
             return 2 - val
        return val

    if sort_by == "severity":
        severity_rank = {
            FindingSeverity.HIGH.value: 3,
            FindingSeverity.MED.value: 2,
            FindingSeverity.LOW.value: 1,
        }
        return sorted(
            items,
            key=lambda item: (
                severity_rank.get(item.severity, 0),
                get_type_rank(item),
                item.created_at.isoformat(),
            ),
            reverse=reverse,
        )
    if sort_by == "path_length":
        return sorted(
            items,
            key=lambda item: (
                (item.path_length if item.path_length is not None else -1),
                get_type_rank(item),
                item.created_at.isoformat(),
            ),
            reverse=reverse,
        )
    # Default sort (created_at)
    return sorted(
        items, 
        key=lambda item: (
            get_type_rank(item),
            item.created_at.isoformat()
        ), 
        reverse=reverse
    )


def _label_payload(item: FindingLabel) -> FindingLabelPayload:
    return FindingLabelPayload(
        id=item.id,
        finding_id=item.finding_id,
        status=item.status,
        fp_reason=item.fp_reason,
        comment=item.comment,
        created_by=item.created_by,
        created_at=item.created_at,
    )


@router.get("/api/v1/projects/{project_id}/results")
def get_project_results_overview(
    request: Request,
    project_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_project_action("finding:read")),
):
    if version_id is not None:
        version = db.get(Version, version_id)
        if version is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="版本不存在")
        if version.project_id != project_id:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="version_id 不属于当前项目",
            )

    if job_id is not None:
        job = db.get(Job, job_id)
        if job is None:
            raise AppError(code="NOT_FOUND", status_code=404, message="任务不存在")
        if job.project_id != project_id:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="job_id 不属于当前项目",
            )

    conditions = [Finding.project_id == project_id]
    if version_id is not None:
        conditions.append(Finding.version_id == version_id)
    if job_id is not None:
        conditions.append(Finding.job_id == job_id)

    rows = db.scalars(select(Finding).where(*conditions)).all()
    items = _dedupe_finding_payloads([_finding_payload(item) for item in rows])

    total = len(items)

    severity_dist = {
        FindingSeverity.HIGH.value: 0,
        FindingSeverity.MED.value: 0,
        FindingSeverity.LOW.value: 0,
    }
    for item in items:
        if item.severity in severity_dist:
            severity_dist[item.severity] += 1

    status_dist = {item.value: 0 for item in FindingStatus}
    vuln_counts: dict[str, int] = {}
    for item in items:
        if item.status in status_dist:
            status_dist[item.status] += 1
        vuln_key = (item.vuln_type or "").strip()
        if vuln_key:
            vuln_counts[vuln_key] = vuln_counts.get(vuln_key, 0) + 1
    vuln_rows = sorted(vuln_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
    top_vuln_types = [
        {"vuln_type": vuln_type, "count": int(count)} for vuln_type, count in vuln_rows
    ]

    payload = ProjectResultOverviewPayload(
        project_id=project_id,
        version_id=version_id,
        job_id=job_id,
        total_findings=int(total),
        severity_dist=severity_dist,
        status_dist=status_dist,
        top_vuln_types=top_vuln_types,
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/scan-results")
def list_scan_results(
    request: Request,
    project_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 200)
    _validate_finding_scope(
        db,
        project_id=project_id,
        version_id=version_id,
        job_id=None,
    )
    normalized_status = _validate_scan_job_status(status)

    conditions = [Job.job_type == JobType.SCAN.value]
    if project_id is not None:
        conditions.append(Job.project_id == project_id)
    if version_id is not None:
        conditions.append(Job.version_id == version_id)
    if normalized_status is not None:
        conditions.append(Job.status == normalized_status)

    if principal.user.role != SystemRole.ADMIN.value:
        if project_id is not None:
            ensure_project_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                project_id=project_id,
                action="finding:read",
            )
        elif version_id is not None:
            ensure_resource_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                action="finding:read",
                resource_type="VERSION",
                resource_id=version_id,
            )
        else:
            conditions.append(
                Job.project_id.in_(
                    select(UserProjectRole.project_id).where(
                        UserProjectRole.user_id == principal.user.id
                    )
                )
            )

    total_stmt = select(func.count()).select_from(Job)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = db.scalar(total_stmt) or 0

    rows = db.execute(
        select(Job, Project, Version)
        .join(Project, Project.id == Job.project_id)
        .join(Version, Version.id == Job.version_id)
        .where(*conditions)
        .order_by(Job.created_at.desc())
        .offset((safe_page - 1) * safe_size)
        .limit(safe_size)
    ).all()
    ai_status_by_scan_job = _map_latest_ai_status_by_scan_job(
        db, scan_job_ids=[job.id for job, _project, _version in rows]
    )

    payload = ScanResultListPayload(
        items=[
            _scan_result_row_payload(
                scan_job=job,
                project=project,
                version=version,
                ai_latest_status=ai_status_by_scan_job.get(job.id),
            )
            for job, project, version in rows
        ],
        total=total,
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/findings")
def list_findings(
    request: Request,
    project_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    severity: str | None = None,
    vuln_type: str | None = None,
    status: str | None = None,
    file_prefix: str | None = None,
    q: str | None = None,
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    normalized_severity = _validate_severity(severity)
    normalized_status = _validate_status(status)
    normalized_sort_by = _validate_sort_by(sort_by)
    normalized_sort_order = _validate_sort_order(sort_order)
    normalized_vuln_type = _normalize_text(vuln_type)
    normalized_file_prefix = _normalize_text(file_prefix)
    normalized_q = _normalize_text(q)
    _validate_finding_scope(
        db,
        project_id=project_id,
        version_id=version_id,
        job_id=job_id,
    )

    if principal.user.role != SystemRole.ADMIN.value:
        if project_id is not None:
            ensure_project_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                project_id=project_id,
                action="finding:read",
            )
        elif version_id is not None:
            ensure_resource_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                action="finding:read",
                resource_type="VERSION",
                resource_id=version_id,
            )
        elif job_id is not None:
            ensure_resource_action(
                db=db,
                user_id=principal.user.id,
                role=principal.user.role,
                action="finding:read",
                resource_type="JOB",
                resource_id=job_id,
            )

    conditions = []
    if project_id is not None:
        conditions.append(Finding.project_id == project_id)
    if version_id is not None:
        conditions.append(Finding.version_id == version_id)
    if job_id is not None:
        conditions.append(Finding.job_id == job_id)
    if normalized_severity is not None:
        conditions.append(Finding.severity == normalized_severity)
    if normalized_status is not None:
        conditions.append(Finding.status == normalized_status)
    if normalized_vuln_type is not None:
        conditions.append(Finding.vuln_type == normalized_vuln_type)
    if normalized_file_prefix is not None:
        conditions.append(Finding.file_path.like(f"{normalized_file_prefix}%"))
    if normalized_q is not None:
        search = f"%{normalized_q}%"
        conditions.append(
            or_(
                Finding.rule_key.ilike(search),
                Finding.vuln_type.ilike(search),
                Finding.file_path.ilike(search),
                Finding.source_file.ilike(search),
                Finding.sink_file.ilike(search),
            )
        )

    if (
        principal.user.role != SystemRole.ADMIN.value
        and project_id is None
        and version_id is None
        and job_id is None
    ):
        conditions.append(
            Finding.project_id.in_(
                select(UserProjectRole.project_id).where(
                    UserProjectRole.user_id == principal.user.id
                )
            )
        )

    rows_stmt = select(Finding)
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = db.scalars(rows_stmt).all()
    latest_assessments = map_latest_finding_ai_assessments(
        db, finding_ids=[item.id for item in rows]
    )
    items = _dedupe_finding_payloads(
        [
            _finding_payload(item, latest_assessment=latest_assessments.get(item.id))
            for item in rows
        ]
    )
    sorted_items = _sort_finding_payloads(
        items,
        sort_by=normalized_sort_by,
        sort_order=normalized_sort_order,
    )
    total = len(sorted_items)
    paged_items = sorted_items[(page - 1) * page_size : page * page_size]

    payload = FindingListPayload(items=paged_items, total=total)
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/findings/{finding_id}")
def get_finding(
    request: Request,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read",
            resource_type="FINDING",
            resource_id_param="finding_id",
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")
    latest_assessment = map_latest_finding_ai_assessments(
        db, finding_ids=[finding.id]
    ).get(finding.id)
    return success_response(
        request,
        data=_finding_payload(
            finding, latest_assessment=latest_assessment
        ).model_dump(),
    )


@router.post("/api/v1/findings/{finding_id}/labels")
def label_finding(
    request: Request,
    finding_id: uuid.UUID,
    payload: FindingLabelRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:label",
            resource_type="FINDING",
            resource_id_param="finding_id",
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")

    next_status = _validate_label_status(payload.status)
    fp_reason = _normalize_text(payload.fp_reason)
    if next_status != FindingStatus.FP.value:
        fp_reason = None

    comment = _normalize_text(payload.comment)
    finding.status = next_status
    label = FindingLabel(
        finding_id=finding.id,
        status=next_status,
        fp_reason=fp_reason,
        comment=comment,
        created_by=principal.user.id,
    )
    db.add(label)
    db.flush()

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="finding.label",
        resource_type="FINDING",
        resource_id=str(finding.id),
        project_id=finding.project_id,
        detail_json={
            "status": next_status,
            "fp_reason": fp_reason,
        },
    )
    db.commit()
    db.refresh(finding)
    db.refresh(label)

    data = FindingLabelActionPayload(
        finding=_finding_payload(finding), label=_label_payload(label)
    )
    return success_response(request, data=data.model_dump())


@router.get("/api/v1/findings/{finding_id}/paths")
def list_finding_paths(
    request: Request,
    finding_id: uuid.UUID,
    mode: str = Query(default="shortest"),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read",
            resource_type="FINDING",
            resource_id_param="finding_id",
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")

    paths = query_finding_paths(db=db, finding=finding, mode=mode, limit=limit)
    payload = FindingPathListPayload(
        finding_id=finding.id,
        mode=mode,
        items=[
            FindingPathPayload(
                path_id=int(item["path_id"]),
                path_length=int(item["path_length"]),
                steps=[FindingPathStepPayload(**step) for step in item["steps"]],
                nodes=[
                    FindingPathNodePayload(**node) for node in item.get("nodes") or []
                ],
                edges=[
                    FindingPathEdgePayload(**edge) for edge in item.get("edges") or []
                ],
            )
            for item in paths
        ],
    )
    return success_response(request, data=payload.model_dump())


@router.get("/api/v1/findings/{finding_id}/path-nodes/{step_id}/context")
def get_finding_path_node_context(
    request: Request,
    finding_id: uuid.UUID,
    step_id: int,
    before: int = Query(default=3, ge=0, le=20),
    after: int = Query(default=3, ge=0, le=20),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "finding:read",
            resource_type="FINDING",
            resource_id_param="finding_id",
        )
    ),
):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="漏洞不存在")

    context = load_finding_path_context(
        db=db,
        finding=finding,
        step_id=step_id,
        before=before,
        after=after,
    )
    payload = FindingPathNodeContextPayload(finding_id=finding.id, **context)
    return success_response(request, data=payload.model_dump())
