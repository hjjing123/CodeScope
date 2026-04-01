from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError, unauthorized_error
from app.models import AuthSession, SystemRole, User, utc_now
from app.security.password import verify_password
from app.security.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
    verify_refresh_token_hash,
)


SELF_REGISTER_ROLE = SystemRole.USER.value


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_session_expired(expires_at: datetime) -> bool:
    return _as_utc(expires_at) <= _as_utc(utc_now())


@dataclass(slots=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    session_id: uuid.UUID


@dataclass(slots=True)
class AuthPrincipal:
    user: User
    session: AuthSession


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _load_user_by_email(*, db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == _normalize_email(email)))


def register(
    *,
    db: Session,
    email: str,
    password_hash: str,
    display_name: str,
    role: str | None,
) -> User:
    normalized_role = role.strip() if role is not None else ""
    if normalized_role == SystemRole.ADMIN.value:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="自注册不支持 Admin 角色",
            detail={"allowed_roles": [SELF_REGISTER_ROLE]},
        )
    if normalized_role not in {"", SELF_REGISTER_ROLE}:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="注册角色不合法",
            detail={"allowed_roles": [SELF_REGISTER_ROLE]},
        )

    normalized_display_name = display_name.strip()
    if not normalized_display_name:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="显示名不能为空",
            detail={"field": "display_name"},
        )

    normalized_email = _normalize_email(email)
    existed = db.scalar(select(User.id).where(User.email == normalized_email))
    if existed is not None:
        raise AppError(
            code="USER_ALREADY_EXISTS", status_code=409, message="用户邮箱已存在"
        )

    user = User(
        email=normalized_email,
        password_hash=password_hash,
        display_name=normalized_display_name,
        role=SELF_REGISTER_ROLE,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def _build_bundle(*, user: User, session_id: uuid.UUID, jti: str) -> TokenBundle:
    settings = get_settings()
    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        session_id=session_id,
        settings=settings,
    )
    refresh_token = create_refresh_token(
        user_id=user.id,
        role=user.role,
        session_id=session_id,
        settings=settings,
        jti=jti,
    )
    return TokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_ttl_minutes * 60,
        refresh_expires_in=settings.refresh_token_ttl_days * 24 * 60 * 60,
        session_id=session_id,
    )


def login(
    *, db: Session, email: str, password: str, ip: str | None, user_agent: str | None
) -> TokenBundle:
    user = _load_user_by_email(db=db, email=email)
    if user is None or not verify_password(password, user.password_hash):
        raise unauthorized_error(message="账号或密码错误", code="AUTH_FAILED")
    if not user.is_active:
        raise AppError(code="USER_DISABLED", status_code=403, message="账号已禁用")
    if user.must_change_password:
        raise AppError(
            code="PASSWORD_CHANGE_REQUIRED",
            status_code=403,
            message="首次登录需先修改密码",
            detail={"required_action": "POST /api/v1/auth/password/first-reset"},
        )

    session_id = uuid.uuid4()
    jti = uuid.uuid4().hex
    bundle = _build_bundle(user=user, session_id=session_id, jti=jti)

    now = utc_now()
    db.add(
        AuthSession(
            id=session_id,
            user_id=user.id,
            jti=jti,
            refresh_token_hash=hash_refresh_token(bundle.refresh_token),
            issued_at=now,
            expires_at=now + timedelta(days=get_settings().refresh_token_ttl_days),
            revoked_at=None,
            ip=ip,
            user_agent=user_agent,
        )
    )
    user.last_login_at = now
    db.commit()
    return bundle


def refresh(
    *, db: Session, refresh_token: str, ip: str | None, user_agent: str | None
) -> TokenBundle:
    settings = get_settings()
    payload = decode_token(
        token=refresh_token, settings=settings, expected_type="refresh"
    )

    user_id = uuid.UUID(str(payload["sub"]))
    session_id = uuid.UUID(str(payload["sid"]))
    jti = str(payload.get("jti", ""))

    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != user_id:
        raise unauthorized_error(message="会话不存在或已失效", code="TOKEN_REVOKED")
    if session.revoked_at is not None or _is_session_expired(session.expires_at):
        raise unauthorized_error(message="会话已失效", code="TOKEN_REVOKED")
    if session.jti != jti:
        raise unauthorized_error(message="刷新令牌已轮换", code="TOKEN_REVOKED")
    if not verify_refresh_token_hash(refresh_token, session.refresh_token_hash):
        raise unauthorized_error(message="刷新令牌校验失败", code="TOKEN_REVOKED")

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized_error(message="用户不存在", code="UNAUTHORIZED")
    if not user.is_active:
        raise AppError(code="USER_DISABLED", status_code=403, message="账号已禁用")
    if user.must_change_password:
        raise AppError(
            code="PASSWORD_CHANGE_REQUIRED",
            status_code=403,
            message="首次登录需先修改密码",
            detail={"required_action": "POST /api/v1/auth/password/first-reset"},
        )

    new_jti = uuid.uuid4().hex
    bundle = _build_bundle(user=user, session_id=session_id, jti=new_jti)
    session.jti = new_jti
    session.refresh_token_hash = hash_refresh_token(bundle.refresh_token)
    session.issued_at = utc_now()
    session.expires_at = utc_now() + timedelta(days=settings.refresh_token_ttl_days)
    session.ip = ip
    session.user_agent = user_agent
    db.commit()
    return bundle


def revoke(*, db: Session, refresh_token: str) -> AuthSession:
    settings = get_settings()
    payload = decode_token(
        token=refresh_token, settings=settings, expected_type="refresh"
    )

    user_id = uuid.UUID(str(payload["sub"]))
    session_id = uuid.UUID(str(payload["sid"]))

    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != user_id:
        raise unauthorized_error(message="会话不存在或已失效", code="TOKEN_REVOKED")
    if not verify_refresh_token_hash(refresh_token, session.refresh_token_hash):
        raise unauthorized_error(message="刷新令牌校验失败", code="TOKEN_REVOKED")

    if session.revoked_at is None:
        session.revoked_at = utc_now()
        db.commit()

    return session


def authenticate_access_token(*, db: Session, access_token: str) -> AuthPrincipal:
    settings = get_settings()
    payload = decode_token(
        token=access_token, settings=settings, expected_type="access"
    )

    user_id = uuid.UUID(str(payload["sub"]))
    session_id = uuid.UUID(str(payload["sid"]))
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != user_id:
        raise unauthorized_error(message="会话不存在或已失效", code="TOKEN_REVOKED")
    if session.revoked_at is not None or _is_session_expired(session.expires_at):
        raise unauthorized_error(message="会话已失效", code="TOKEN_REVOKED")

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized_error(message="用户不存在", code="UNAUTHORIZED")
    if not user.is_active:
        raise AppError(code="USER_DISABLED", status_code=403, message="账号已禁用")
    if user.must_change_password:
        raise AppError(
            code="PASSWORD_CHANGE_REQUIRED",
            status_code=403,
            message="首次登录需先修改密码",
            detail={"required_action": "POST /api/v1/auth/password/first-reset"},
        )

    return AuthPrincipal(user=user, session=session)


def first_password_reset(
    *,
    db: Session,
    email: str,
    current_password: str,
    new_password_hash: str,
) -> User:
    user = _load_user_by_email(db=db, email=email)
    if user is None or not verify_password(current_password, user.password_hash):
        raise unauthorized_error(message="账号或密码错误", code="AUTH_FAILED")
    if not user.is_active:
        raise AppError(code="USER_DISABLED", status_code=403, message="账号已禁用")
    if not user.must_change_password:
        raise AppError(
            code="PASSWORD_RESET_NOT_REQUIRED",
            status_code=409,
            message="当前账号不需要执行首次改密",
        )

    user.password_hash = new_password_hash
    user.must_change_password = False

    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    db.flush()
    return user
