"""Identifikatsiya jadvallari (migratsiya 0003 bilan bir xil)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(300))


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    scope_all: Mapped[bool]
    is_system: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(
        ForeignKey("core.roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("core.permissions.code", ondelete="CASCADE"), primary_key=True
    )


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(ForeignKey("core.roles.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PositionBranch(Base):
    __tablename__ = "position_branches"
    position_id: Mapped[int] = mapped_column(
        ForeignKey("core.positions.id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    position_id: Mapped[int] = mapped_column(ForeignKey("core.positions.id"))
    password_hash: Mapped[str] = mapped_column(Text)
    password_changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    must_change_password: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PasswordHistory(Base):
    __tablename__ = "password_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BackupCode(Base):
    __tablename__ = "backup_codes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    code_hmac: Mapped[bytes] = mapped_column(LargeBinary)
    used_at: Mapped[datetime | None]


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    idle_expires_at: Mapped[datetime]
    absolute_expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoke_reason: Mapped[str | None] = mapped_column(String(32))
    ip_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    ua_summary: Mapped[str] = mapped_column(String(80), default="")


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)
    used_at: Mapped[datetime | None]
    pending_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
