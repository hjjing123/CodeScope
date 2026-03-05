from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.response import get_request_id, success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_principal
from app.schemas.auth import (
    AuthTokenPayload,
    FirstPasswordResetRequest,
    LoginRequest,
    MePayload,
    PermissionPayload,
    RegisterPayload,
    RegisterRequest,
    RefreshRequest,
    RevokeRequest,
)
from app.security.password import hash_password
from app.services.audit_service import append_audit_log
from app.services.auth_service import (
    AuthPrincipal,
    first_password_reset,
    login,
    refresh,
    register,
    revoke,
)
from app.services.authorization_service import list_context_actions


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
AUTH_COOKIE_KEY = "token"


def _set_access_cookie(response, access_token: str, expires_in: int) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_KEY,
        value=access_token,
        max_age=expires_in,
        httponly=False,
        secure=False,
        samesite="lax",
        path="/",
    )


@router.post("/register")
def register_api(
    request: Request, payload: RegisterRequest, db: Session = Depends(get_db)
):
    user = register(
        db=db,
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=payload.role,
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=user.id,
        action="auth.register",
        resource_type="USER",
        resource_id=str(user.id),
        detail_json={"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)

    data = RegisterPayload(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
    )
    return success_response(request, data=data.model_dump(), status_code=201)


@router.post("/login")
def login_api(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    bundle = login(
        db=db,
        email=payload.email,
        password=payload.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    data = AuthTokenPayload(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        token_type=bundle.token_type,
        expires_in=bundle.expires_in,
        refresh_expires_in=bundle.refresh_expires_in,
        session_id=bundle.session_id,
    )
    response = success_response(request, data=data.model_dump())
    _set_access_cookie(response, bundle.access_token, bundle.expires_in)
    return response


@router.post("/refresh")
def refresh_api(
    request: Request, payload: RefreshRequest, db: Session = Depends(get_db)
):
    bundle = refresh(
        db=db,
        refresh_token=payload.refresh_token,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    data = AuthTokenPayload(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        token_type=bundle.token_type,
        expires_in=bundle.expires_in,
        refresh_expires_in=bundle.refresh_expires_in,
        session_id=bundle.session_id,
    )
    response = success_response(request, data=data.model_dump())
    _set_access_cookie(response, bundle.access_token, bundle.expires_in)
    return response


@router.post("/revoke")
def revoke_api(request: Request, payload: RevokeRequest, db: Session = Depends(get_db)):
    session = revoke(db=db, refresh_token=payload.refresh_token)
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=session.user_id,
        action="auth.revoke",
        resource_type="SESSION",
        resource_id=str(session.id),
    )
    db.commit()
    response = success_response(
        request, data={"revoked": True, "session_id": str(session.id)}
    )
    response.delete_cookie(key=AUTH_COOKIE_KEY, path="/")
    return response


@router.post("/password/first-reset")
def first_password_reset_api(
    request: Request,
    payload: FirstPasswordResetRequest,
    db: Session = Depends(get_db),
):
    user = first_password_reset(
        db=db,
        email=payload.email,
        current_password=payload.current_password,
        new_password_hash=hash_password(payload.new_password),
    )
    append_audit_log(
        db,
        request_id=get_request_id(request),
        operator_user_id=user.id,
        action="auth.first_password_reset",
        resource_type="USER",
        resource_id=str(user.id),
        detail_json={"email": user.email},
    )
    db.commit()
    return success_response(request, data={"password_reset": True})


@router.get("/me")
def me_api(request: Request, principal: AuthPrincipal = Depends(get_current_principal)):
    data = MePayload(
        id=principal.user.id,
        email=principal.user.email,
        display_name=principal.user.display_name,
        role=principal.user.role,
        is_active=principal.user.is_active,
        must_change_password=principal.user.must_change_password,
    )
    return success_response(request, data=data.model_dump())


@router.get("/permissions")
def permissions_api(
    request: Request,
    project_id: uuid.UUID | None = None,
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    actions, project_role = list_context_actions(
        db=db,
        user_id=principal.user.id,
        role=principal.user.role,
        project_id=project_id,
    )
    data = PermissionPayload(
        scope_type="project" if project_id is not None else "platform",
        scope_id=project_id,
        role=principal.user.role,
        project_role=project_role,
        actions=sorted(actions),
    )
    return success_response(request, data=data.model_dump())
