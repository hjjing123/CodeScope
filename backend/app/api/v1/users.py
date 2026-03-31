from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import require_platform_action
from app.models import SystemRole, User
from app.schemas.user import UserListPayload, UserPayload, UserUpdateRequest
from app.services.audit_service import append_audit_log
from app.services.auth_service import AuthPrincipal


router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _validate_system_role(role: str) -> str:
    valid = {item.value for item in SystemRole}
    if role not in valid:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="角色值不合法",
            detail={"allowed_roles": sorted(valid)},
        )
    return role


def _active_admin_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == SystemRole.ADMIN.value,
                User.is_active.is_(True),
            )
        )
        or 0
    )


@router.get("")
def list_users(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 200)

    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User)
        .order_by(User.created_at.desc())
        .offset((safe_page - 1) * safe_size)
        .limit(safe_size)
    ).all()

    data = UserListPayload(
        items=[
            UserPayload(
                id=row.id,
                email=row.email,
                display_name=row.display_name,
                role=row.role,
                is_active=row.is_active,
                must_change_password=row.must_change_password,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
    )
    return success_response(request, data=data.model_dump())


@router.patch("/{user_id}")
def update_user(
    request: Request,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    user = db.get(User, user_id)
    if user is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="用户不存在")

    changes: dict[str, object] = {}
    if payload.display_name is not None and payload.display_name != user.display_name:
        changes["display_name"] = {
            "before": user.display_name,
            "after": payload.display_name,
        }
        user.display_name = payload.display_name
    if payload.role is not None:
        role = _validate_system_role(payload.role)
        if role != user.role:
            changes["role"] = {"before": user.role, "after": role}
            user.role = role
    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = {"before": user.is_active, "after": payload.is_active}
        user.is_active = payload.is_active

    if not changes:
        data = UserPayload(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
        )
        return success_response(request, data=data.model_dump())

    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.update",
        resource_type="USER",
        resource_id=str(user.id),
        detail_json=changes,
    )
    db.commit()
    db.refresh(user)

    data = UserPayload(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )
    return success_response(request, data=data.model_dump())


@router.delete("/{user_id}")
def delete_user(
    request: Request,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_platform_action("system:config")),
):
    user = db.get(User, user_id)
    if user is None:
        raise AppError(code="NOT_FOUND", status_code=404, message="用户不存在")
    if user.id == principal.user.id:
        raise AppError(
            code="SELF_DELETE_FORBIDDEN",
            status_code=409,
            message="禁止删除当前登录管理员",
        )
    if (
        user.role == SystemRole.ADMIN.value
        and user.is_active
        and _active_admin_count(db) == 1
    ):
        raise AppError(
            code="LAST_ADMIN_PROTECTED",
            status_code=409,
            message="禁止删除最后一个活跃管理员",
        )

    db.delete(user)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=principal.user.id,
        action="user.delete",
        resource_type="USER",
        resource_id=str(user.id),
        detail_json={"email": user.email, "role": user.role},
    )
    db.commit()
    return success_response(request, data={"removed": True})
