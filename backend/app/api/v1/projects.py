from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action, require_project_action
from app.models import Project, ProjectRole, ProjectStatus, SystemRole, UserProjectRole
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectListPayload,
    ProjectPayload,
    ProjectUpdateRequest,
)
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal
from app.services.project_service import (
    cleanup_project_local_artifacts,
    cleanup_project_task_log_index,
    collect_project_resource_ids,
)


router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _project_payload(
    *, project: Project, my_project_role: str | None
) -> ProjectPayload:
    return ProjectPayload(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        my_project_role=my_project_role,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("")
def create_project(
    request: Request,
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("project:write")),
):
    project_name = payload.name.strip()
    if not project_name:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="项目名称不能为空",
        )

    project = Project(
        name=project_name,
        description=payload.description,
        status=ProjectStatus.NEW.value,
    )
    db.add(project)
    db.flush()

    member = UserProjectRole(
        project_id=project.id,
        user_id=principal.user.id,
        project_role=ProjectRole.OWNER.value,
        granted_by=principal.user.id,
    )
    db.add(member)

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="project.create",
        resource_type="PROJECT",
        resource_id=str(project.id),
        project_id=project.id,
        detail_json={"name": project.name},
    )

    db.commit()
    db.refresh(project)
    return success_response(
        request,
        data=_project_payload(
            project=project, my_project_role=ProjectRole.OWNER.value
        ).model_dump(),
        status_code=201,
    )


@router.get("")
def list_projects(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("project:read")),
):
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 200)

    if principal.user.role == SystemRole.ADMIN.value:
        total = db.scalar(select(func.count()).select_from(Project)) or 0
        rows = db.scalars(
            select(Project)
            .order_by(Project.created_at.desc())
            .offset((safe_page - 1) * safe_size)
            .limit(safe_size)
        ).all()
        payload = ProjectListPayload(
            items=[
                _project_payload(project=item, my_project_role=None) for item in rows
            ],
            total=total,
        )
        return success_response(request, data=payload.model_dump())

    total = (
        db.scalar(
            select(func.count())
            .select_from(UserProjectRole)
            .where(UserProjectRole.user_id == principal.user.id)
        )
        or 0
    )
    rows = db.execute(
        select(Project, UserProjectRole.project_role)
        .join(UserProjectRole, UserProjectRole.project_id == Project.id)
        .where(UserProjectRole.user_id == principal.user.id)
        .order_by(Project.created_at.desc())
        .offset((safe_page - 1) * safe_size)
        .limit(safe_size)
    ).all()

    payload = ProjectListPayload(
        items=[
            _project_payload(project=project, my_project_role=project_role)
            for project, project_role in rows
        ],
        total=total,
    )
    return success_response(request, data=payload.model_dump())


@router.get("/{project_id}")
def get_project(
    request: Request,
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:read")),
):
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    project_role: str | None = None
    if principal.user.role != SystemRole.ADMIN.value:
        membership = db.scalar(
            select(UserProjectRole.project_role).where(
                UserProjectRole.user_id == principal.user.id,
                UserProjectRole.project_id == project_id,
            )
        )
        project_role = membership

    return success_response(
        request,
        data=_project_payload(
            project=project, my_project_role=project_role
        ).model_dump(),
    )


@router.patch("/{project_id}")
def update_project(
    request: Request,
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    changes: dict[str, object] = {}
    if payload.description is not None and payload.description != project.description:
        changes["description"] = {
            "before": project.description,
            "after": payload.description,
        }
        project.description = payload.description

    if changes:
        append_audit_log(
            db,
            request_id=get_request_id(request),
            operator_user_id=principal.user.id,
            action="project.update",
            resource_type="PROJECT",
            resource_id=str(project.id),
            project_id=project.id,
            detail_json=changes,
        )
        db.commit()
        db.refresh(project)

    project_role: str | None = None
    if principal.user.role != SystemRole.ADMIN.value:
        project_role = db.scalar(
            select(UserProjectRole.project_role).where(
                UserProjectRole.user_id == principal.user.id,
                UserProjectRole.project_id == project_id,
            )
        )

    return success_response(
        request,
        data=_project_payload(
            project=project, my_project_role=project_role
        ).model_dump(),
    )


@router.delete("/{project_id}")
def delete_project(
    request: Request,
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:delete")),
):
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目不存在")

    version_ids, job_ids, import_job_ids = collect_project_resource_ids(
        db, project_id=project_id
    )
    cleanup_project_task_log_index(db, project_id=project_id)
    db.delete(project)

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="project.delete",
        resource_type="PROJECT",
        resource_id=str(project_id),
        project_id=project_id,
    )
    db.commit()

    cleanup_project_local_artifacts(
        version_ids=version_ids,
        job_ids=job_ids,
        import_job_ids=import_job_ids,
    )
    return success_response(request, data={"deleted": True})
