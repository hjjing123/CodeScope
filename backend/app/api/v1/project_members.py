from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import require_project_action
from app.models import ProjectRole, User, UserProjectRole
from app.schemas.member import (
    ProjectMemberCreateRequest,
    ProjectMemberListPayload,
    ProjectMemberPayload,
    ProjectMemberUpdateRequest,
)
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal


router = APIRouter(prefix="/api/v1/projects/{project_id}/members", tags=["project-members"])


def _validate_project_role(project_role: str) -> str:
    valid = {item.value for item in ProjectRole}
    if project_role not in valid:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="项目角色值不合法",
            detail={"allowed_roles": sorted(valid)},
        )
    return project_role


def _owner_count(db: Session, project_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(UserProjectRole)
            .where(
                UserProjectRole.project_id == project_id,
                UserProjectRole.project_role == ProjectRole.OWNER.value,
            )
        )
        or 0
    )


@router.get("")
def list_project_members(
    request: Request,
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_project_action("project:read")),
):
    rows = db.scalars(
        select(UserProjectRole)
        .where(UserProjectRole.project_id == project_id)
        .order_by(UserProjectRole.created_at.asc())
    ).all()
    data = ProjectMemberListPayload(
        items=[
            ProjectMemberPayload(
                user_id=row.user_id,
                project_id=row.project_id,
                project_role=row.project_role,
                granted_by=row.granted_by,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=len(rows),
    )
    return success_response(request, data=data.model_dump())


@router.post("")
def add_project_member(
    request: Request,
    project_id: uuid.UUID,
    payload: ProjectMemberCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    target_user = db.get(User, payload.user_id)
    if target_user is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="目标用户不存在")

    existed = db.scalar(
        select(UserProjectRole).where(
            UserProjectRole.project_id == project_id,
            UserProjectRole.user_id == payload.user_id,
        )
    )
    if existed is not None:
        raise AppError(code="PROJECT_MEMBER_EXISTS", status_code=409, message="用户已是项目成员")

    member = UserProjectRole(
        user_id=payload.user_id,
        project_id=project_id,
        project_role=_validate_project_role(payload.project_role),
        granted_by=principal.user.id,
    )
    db.add(member)
    db.flush()

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="project.member.add",
        resource_type="PROJECT_MEMBER",
        resource_id=f"{project_id}:{payload.user_id}",
        project_id=project_id,
        detail_json={"project_role": member.project_role},
    )

    db.commit()
    db.refresh(member)
    data = ProjectMemberPayload(
        user_id=member.user_id,
        project_id=member.project_id,
        project_role=member.project_role,
        granted_by=member.granted_by,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )
    return success_response(request, data=data.model_dump(), status_code=201)


@router.patch("/{user_id}")
def update_project_member(
    request: Request,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProjectMemberUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    member = db.scalar(
        select(UserProjectRole).where(
            UserProjectRole.project_id == project_id,
            UserProjectRole.user_id == user_id,
        )
    )
    if member is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目成员不存在")

    next_role = _validate_project_role(payload.project_role)
    if member.project_role == ProjectRole.OWNER.value and next_role != ProjectRole.OWNER.value:
        if _owner_count(db, project_id) == 1:
            raise AppError(
                code="LAST_OWNER_PROTECTED",
                status_code=409,
                message="禁止降级项目最后一个 Owner",
            )

    before_role = member.project_role
    member.project_role = next_role

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="project.member.update",
        resource_type="PROJECT_MEMBER",
        resource_id=f"{project_id}:{user_id}",
        project_id=project_id,
        detail_json={"before": before_role, "after": next_role},
    )

    db.commit()
    db.refresh(member)
    data = ProjectMemberPayload(
        user_id=member.user_id,
        project_id=member.project_id,
        project_role=member.project_role,
        granted_by=member.granted_by,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )
    return success_response(request, data=data.model_dump())


@router.delete("/{user_id}")
def remove_project_member(
    request: Request,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_project_action("project:write")),
):
    member = db.scalar(
        select(UserProjectRole).where(
            UserProjectRole.project_id == project_id,
            UserProjectRole.user_id == user_id,
        )
    )
    if member is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目成员不存在")

    if member.project_role == ProjectRole.OWNER.value and _owner_count(db, project_id) == 1:
        raise AppError(
            code="LAST_OWNER_PROTECTED",
            status_code=409,
            message="禁止删除项目最后一个 Owner",
        )

    db.delete(member)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="project.member.remove",
        resource_type="PROJECT_MEMBER",
        resource_id=f"{project_id}:{user_id}",
        project_id=project_id,
    )
    db.commit()
    return success_response(request, data={"removed": True})
