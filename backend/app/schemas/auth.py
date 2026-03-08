from __future__ import annotations

import uuid
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=255)
    role: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class RevokeRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class FirstPasswordResetRequest(BaseModel):
    email: EmailStr
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class AuthTokenPayload(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    session_id: uuid.UUID


class RegisterPayload(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool


class MePayload(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool


class PermissionPayload(BaseModel):
    scope_type: str
    scope_id: uuid.UUID | None
    role: str
    project_role: str | None
    actions: list[str]
