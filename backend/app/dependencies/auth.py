from __future__ import annotations

import uuid

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError, unauthorized_error
from app.db.session import get_db
from app.services.auth_service import AuthPrincipal, authenticate_access_token
from app.services.authorization_service import (
    ensure_platform_action,
    ensure_project_action,
    ensure_resource_action,
)


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise unauthorized_error()

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise unauthorized_error()
    return parts[1].strip()


def get_current_principal(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    token = _extract_bearer_token(authorization)
    principal = authenticate_access_token(db=db, access_token=token)
    request.state.operator_user_id = principal.user.id
    request.state.operator_role = principal.user.role
    return principal


def require_platform_action(action: str):
    def dependency(
        principal: AuthPrincipal = Depends(get_current_principal),
    ) -> AuthPrincipal:
        ensure_platform_action(role=principal.user.role, action=action)
        return principal

    return dependency


def require_project_action(action: str):
    def dependency(
        project_id: uuid.UUID,
        principal: AuthPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> AuthPrincipal:
        ensure_project_action(
            db=db,
            user_id=principal.user.id,
            role=principal.user.role,
            project_id=project_id,
            action=action,
        )
        return principal

    return dependency


def require_project_resource_action(
    action: str,
    *,
    resource_type: str,
    resource_id_param: str = "resource_id",
):
    def dependency(
        request: Request,
        principal: AuthPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> AuthPrincipal:
        resource_id = request.path_params.get(resource_id_param)
        if resource_id is None:
            raise AppError(
                code="INVALID_ARGUMENT",
                status_code=422,
                message="缺少资源标识参数",
                detail={"resource_id_param": resource_id_param},
            )

        ensure_resource_action(
            db=db,
            user_id=principal.user.id,
            role=principal.user.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return principal

    return dependency
