"""Auth API sxemalari. Kirishda noma'lum maydonlar rad etiladi."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auth import passwords
from app.auth.context import AuthContext


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginOut(BaseModel):
    next: Literal["mfa_verify", "mfa_enroll"]
    mfa_token: str


class MfaTokenIn(_In):
    mfa_token: str = Field(min_length=20, max_length=128)


class MfaIn(MfaTokenIn):
    code: str = Field(min_length=6, max_length=16)


class EnrollStartOut(BaseModel):
    otpauth_uri: str
    qr_svg_data_uri: str
    secret: str


class MeOut(BaseModel):
    id: int
    username: str
    full_name: str
    role_code: str
    permissions: list[str]
    branch_ids: list[int] | None
    must_change_password: bool
    password_min_length: int


class EnrollConfirmOut(BaseModel):
    user: MeOut
    backup_codes: list[str]


class PasswordChangeIn(_In):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    ua_summary: str
    ip: str | None
    current: bool


def me_out(ctx: AuthContext) -> MeOut:
    return MeOut(
        id=ctx.user_id,
        username=ctx.username,
        full_name=ctx.full_name,
        role_code=ctx.role_code,
        permissions=sorted(ctx.permissions),
        branch_ids=None if ctx.branch_ids is None else sorted(ctx.branch_ids),
        must_change_password=ctx.must_change_password,
        password_min_length=passwords.min_length(),
    )
