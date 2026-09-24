"""Server tomonidagi sessiyalar (spec 3.2). DB'da token emas, uning HMAC'i saqlanadi."""

from __future__ import annotations

import base64
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.auth.models import User, UserSession
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose, keyed_hash

SLIDE_EVERY = timedelta(seconds=60)
_BROWSERS = (
    ("Edg/", "Edge"), ("OPR/", "Opera"), ("YaBrowser", "Яндекс"),
    ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"),
)
_OSES = (
    ("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iOS"),
    ("iPad", "iPadOS"), ("Mac OS X", "macOS"), ("Linux", "Linux"),
)


@dataclass(frozen=True, slots=True)
class NewSession:
    id: uuid.UUID
    token: str
    csrf: str
    absolute_expires_at: datetime


def token_hmac(token: str) -> bytes:
    return keyed_hash(keystore.pepper(), "session", token)


def csrf_for(token: str) -> str:
    """Signed double-submit: CSRF qiymati sessiya tokenidan chiqariladi (M1)."""
    digest = keyed_hash(keystore.pepper(), "csrf", token)
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def ip_aad(session_id: uuid.UUID) -> str:
    return f"core.sessions.ip_enc:{session_id}"


def ua_summary(ua: str | None) -> str:
    if not ua:
        return "—"
    browser = next((name for token, name in _BROWSERS if token in ua), "Браузер")
    system = next((name for token, name in _OSES if token in ua), "")
    return f"{browser} · {system}" if system else browser


def create(
    db: Session,
    user_id: int,
    ip: str | None,
    ua: str | None,
    now: datetime,
    *,
    absolute_expires_at: datetime | None = None,
) -> NewSession:
    """`absolute_expires_at` — sessiya aylantirilganda (fix r2, M8) eskisining absolyut
    muddatini meros qilib olish uchun; berilsa, standart muddat bilan solishtirib
    ENG ERTASI olinadi (parol almashtirish sessiyani "abadiylashtirmasin")."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    session_id = uuid.uuid4()
    default_absolute = now + timedelta(hours=settings.session_absolute_hours)
    absolute = (
        min(default_absolute, absolute_expires_at)
        if absolute_expires_at is not None
        else default_absolute
    )
    db.add(
        UserSession(
            id=session_id,
            user_id=user_id,
            token_hmac=token_hmac(token),
            created_at=now,
            last_seen_at=now,
            idle_expires_at=min(now + timedelta(minutes=settings.session_idle_minutes), absolute),
            absolute_expires_at=absolute,
            ip_enc=keystore.encrypt_str(Purpose.PII, ip, ip_aad(session_id)) if ip else None,
            ua_summary=ua_summary(ua)[:80],
        )
    )
    db.flush()
    return NewSession(session_id, token, csrf_for(token), absolute)


def resolve(db: Session, token: str, now: datetime) -> tuple[UserSession, User] | None:
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hmac == token_hmac(token))
    ).first()
    if row is None:
        return None
    sess, user = row
    if (
        sess.revoked_at is not None
        or sess.idle_expires_at <= now
        or sess.absolute_expires_at <= now
        or not user.is_active
    ):
        return None
    if now - sess.last_seen_at >= SLIDE_EVERY:
        idle = timedelta(minutes=get_settings().session_idle_minutes)
        sess.last_seen_at = now
        sess.idle_expires_at = min(now + idle, sess.absolute_expires_at)
    return sess, user


def revoke(db: Session, session_id: uuid.UUID, reason: str, now: datetime) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason=reason)
    )


def revoke_all(
    db: Session, user_id: int, reason: str, now: datetime, except_id: uuid.UUID | None = None
) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason=reason)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    return cast(CursorResult[Any], db.execute(stmt)).rowcount
