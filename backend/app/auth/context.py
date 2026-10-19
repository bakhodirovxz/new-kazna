"""Har so'rov uchun "kim va nimaga haqli" (spec 3.3-3.4). Tekshiruv faqat serverda."""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.models import Position, PositionBranch, Role, RolePermission, User
from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import DB, apply_rls
from app.core.errors import AuthError, ForbiddenError, PasswordChangeRequired, ScopeViolationError

SESSION_COOKIE = "__Host-ugk_session"
CSRF_COOKIE = "__Host-ugk_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PASSWORD_CHANGE_ALLOWED = frozenset(
    {"/api/v1/auth/me", "/api/v1/auth/password/change", "/api/v1/auth/logout"}
)


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: int
    username: str
    full_name: str
    role_code: str
    permissions: frozenset[str]
    branch_ids: frozenset[int] | None  # None — barcha filiallar
    session_id: uuid.UUID
    must_change_password: bool = False

    def has(self, perm: str) -> bool:
        return perm in self.permissions

    def require(self, *perms: str) -> None:
        if not all(p in self.permissions for p in perms):
            raise ForbiddenError()

    def assert_branch(self, branch_id: int | None) -> None:
        """So'ralgan filial foydalanuvchi doirasida ekanini tekshiradi (`None` — "hammasi")."""
        if branch_id is None or self.branch_ids is None:
            return
        if branch_id not in self.branch_ids:
            raise ScopeViolationError(branch_id=branch_id)


def load_scope(db: Session, user: User) -> tuple[str, frozenset[str], frozenset[int] | None]:
    row = db.execute(
        select(Role.id, Role.code, Role.scope_all)
        .join(Position, Position.role_id == Role.id)
        .where(Position.id == user.position_id, Position.is_active.is_(True))
    ).one_or_none()
    if row is None:
        return "", frozenset(), frozenset()
    role_id, role_code, scope_all = row
    perms = frozenset(
        db.execute(
            select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
        ).scalars()
    )
    if scope_all:
        return role_code, perms, None
    branches = frozenset(
        db.execute(
            select(PositionBranch.branch_id).where(PositionBranch.position_id == user.position_id)
        ).scalars()
    )
    return role_code, perms, branches


def build_context(db: Session, user: User, session_id: uuid.UUID, now: datetime) -> AuthContext:
    role_code, perms, branches = load_scope(db, user)
    max_age = timedelta(days=get_settings().password_max_age_days)
    return AuthContext(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role_code=role_code,
        permissions=perms,
        branch_ids=branches,
        session_id=session_id,
        must_change_password=user.must_change_password or user.password_changed_at + max_age <= now,
    )


def csrf_ok(session_token: str, cookie: str | None, header: str | None) -> bool:
    """Signed double-submit (M1): cookie == header == HMAC(pepper, "csrf", session_token).

    Doim `bytes` sifatida solishtiriladi — `hmac.compare_digest` ASCII bo'lmagan `str`
    juftliklarida `TypeError` beradi (I1), shu bois qiymatlar oldindan `utf-8`'ga o'giriladi.

    Ommaviy: `router.logout` sessiyasi ixtiyoriy bo'lgani uchun `Ctx` dependency'siz ham
    CSRF'ni tekshirishi kerak (M11 — fix round 1).
    """
    if cookie is None or header is None:
        return False
    cookie_b = cookie.encode("utf-8")
    header_b = header.encode("utf-8")
    expected_b = sessions.csrf_for(session_token).encode("utf-8")
    return hmac.compare_digest(cookie_b, header_b) and hmac.compare_digest(header_b, expected_b)


def get_ctx(
    request: Request,
    db: DB,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> AuthContext:
    if not session_cookie:
        raise AuthError("unauthenticated")
    now = datetime.now(UTC)
    resolved = sessions.resolve(db, session_cookie, now)
    if resolved is None:
        raise AuthError("session_expired")
    sess, user = resolved
    if request.method not in SAFE_METHODS and not csrf_ok(
        session_cookie, csrf_cookie, csrf_header
    ):
        raise ForbiddenError("csrf_failed")
    ratelimit.check("api_user", str(user.id), ratelimit.API_PER_USER)
    ctx = build_context(db, user, sess.id, now)
    if ctx.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED:
        raise PasswordChangeRequired()
    apply_rls(db, ctx.branch_ids)
    request.state.auth = ctx
    request.state.user_id = user.id
    return ctx


Ctx = Annotated[AuthContext, Depends(get_ctx)]


def require_perm(*perms: str) -> Callable[..., AuthContext]:
    """Endpoint ruxsati. Deny-by-default: tests/test_route_guards.py har route'ni tekshiradi."""
    if not perms:
        raise ValueError("require_perm() kamida bitta ruxsat talab qiladi")

    def dependency(request: Request, ctx: Ctx) -> AuthContext:
        try:
            ctx.require(*perms)
        except ForbiddenError:
            # Ledger (fix r1): faqat ruxsat YETISHMASLIGI auditga yoziladi — conflict'lar
            # (last_admin, cannot_modify_self va h.k.) bu yerdan o'tmaydi, ular allaqachon
            # autentifikatsiyadan o'tgan, faqat amal rad etilgan holatlar (deferred ledger).
            from app.audit.service import AuditAction, log_event
            from app.core.request_meta import client_meta

            log_event(
                client_meta(request),
                AuditAction.ACCESS_DENIED,
                user_id=ctx.user_id,
                result="denied",
                details={"path": request.url.path, "required": sorted(perms)},
            )
            raise
        return ctx

    dependency.required_perms = frozenset(perms)  # type: ignore[attr-defined]
    return dependency
