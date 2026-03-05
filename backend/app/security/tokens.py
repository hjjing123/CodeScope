from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import Settings
from app.core.errors import AppError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_refresh_token_hash(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(token), expected_hash)


def _encode(payload: dict[str, object], settings: Settings) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _base_payload(
    *,
    user_id: uuid.UUID,
    role: str,
    session_id: uuid.UUID,
    token_type: str,
    expires_at: datetime,
) -> dict[str, object]:
    now = utc_now()
    return {
        "sub": str(user_id),
        "role": role,
        "sid": str(session_id),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def create_access_token(*, user_id: uuid.UUID, role: str, session_id: uuid.UUID, settings: Settings) -> str:
    expires_at = utc_now() + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = _base_payload(
        user_id=user_id,
        role=role,
        session_id=session_id,
        token_type="access",
        expires_at=expires_at,
    )
    return _encode(payload, settings)


def create_refresh_token(
    *,
    user_id: uuid.UUID,
    role: str,
    session_id: uuid.UUID,
    settings: Settings,
    jti: str,
) -> str:
    expires_at = utc_now() + timedelta(days=settings.refresh_token_ttl_days)
    payload = _base_payload(
        user_id=user_id,
        role=role,
        session_id=session_id,
        token_type="refresh",
        expires_at=expires_at,
    )
    payload["jti"] = jti
    return _encode(payload, settings)


def decode_token(*, token: str, settings: Settings, expected_type: str) -> dict[str, object]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(code="UNAUTHORIZED", status_code=401, message="令牌已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(code="UNAUTHORIZED", status_code=401, message="令牌无效") from exc

    token_type = payload.get("typ")
    if token_type != expected_type:
        raise AppError(code="UNAUTHORIZED", status_code=401, message="令牌类型不正确")

    return payload
