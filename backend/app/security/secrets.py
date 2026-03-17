from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.core.errors import AppError


def _build_fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="密钥不能为空",
        )
    return _build_fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="密钥不能为空",
        )
    try:
        return _build_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError(
            code="AI_SECRET_DECRYPT_FAILED",
            status_code=500,
            message="AI 密钥解密失败",
        ) from exc


def mask_secret(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:3]}{'*' * (len(normalized) - 7)}{normalized[-4:]}"
