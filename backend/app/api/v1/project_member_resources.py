from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_project_resource_action
from app.models import UserProjectRole
from app.schemas.member import ProjectMemberPayload
from app.services.auth_service import AuthPrincipal


router = APIRouter(prefix="/api/v1/project-members", tags=["project-members"])


@router.get("/{member_id}")
def get_project_member_by_id(
    request: Request,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(
        require_project_resource_action(
            "project:read",
            resource_type="PROJECT_MEMBER",
            resource_id_param="member_id",
        )
    ),
):
    member = db.get(UserProjectRole, member_id)
    if member is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="项目成员不存在")

    data = ProjectMemberPayload(
        user_id=member.user_id,
        project_id=member.project_id,
        project_role=member.project_role,
        granted_by=member.granted_by,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )
    return success_response(request, data=data.model_dump())
