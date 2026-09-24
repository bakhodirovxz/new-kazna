"""Autentifikatsiya oqimlari (spec 3.1): parol → 2FA challenge → sessiya."""

from __future__ import annotations

import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, NoReturn

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth import passwords, sessions, totp
from app.auth.context import AuthContext
from app.auth.models import BackupCode, MfaChallenge, PasswordHistory, User, UserSession
from app.auth.schemas import SessionOut
from app.core import keystore, ratelimit
from app.core.config import get_settings
from app.core.crypto import CryptoError, Purpose, keyed_hash
from app.core.errors import AuthError, ConflictError, NotFoundError, ValidationFailed
from app.core.request_meta import ClientMeta

MFA_CHALLENGE_TTL = timedelta(minutes=5)
MFA_MAX_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class LoginResult:
    next: Literal["mfa_verify", "mfa_enroll"]
    mfa_token: str


@dataclass(frozen=True, slots=True)
class EnrollStart:
    otpauth_uri: str
    qr_svg_data_uri: str
    secret: str


def normalize_username(raw: str) -> str:
    return unicodedata.normalize("NFKC", raw).strip().lower()


def totp_aad(user_id: int) -> str:
    return f"core.users.totp_secret_enc:{user_id}"


def _challenge_hmac(token: str) -> bytes:
    return keyed_hash(keystore.pepper(), "mfa", token)


def _backup_hmac(user_id: int, normalized: str) -> bytes:
    return keyed_hash(keystore.pepper(), "backup", f"{user_id}:{normalized}")


def login(
    db: Session, username: str, password: str, meta: ClientMeta, now: datetime
) -> LoginResult:
    settings = get_settings()
    ratelimit.check("login_ip", meta.ip or "unknown", ratelimit.LOGIN_PER_IP)
    uname = normalize_username(username)
    user = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
    if user is None:
        passwords.dummy_verify(password)
        log_event(meta, AuditAction.LOGIN_FAIL, user_id=None, result="fail",
                  details={"username": uname[:64], "reason": "unknown_user"})
        raise AuthError("invalid_credentials")

    password_ok = passwords.verify_password(password, user.password_hash)
    locked = user.locked_until is not None and user.locked_until > now
    if not user.is_active or locked or not password_ok:
        reason = "inactive" if not user.is_active else "locked" if locked else "bad_password"
        if reason == "bad_password":
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_logins = 0
                reason = "locked_now"
            db.commit()  # so'rov rollback bo'lsa ham hisoblagich saqlanadi
        log_event(meta, AuditAction.LOGIN_FAIL, user_id=user.id, result="fail",
                  details={"reason": reason})
        raise AuthError("invalid_credentials")

    user.failed_logins = 0
    user.locked_until = None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    kind: Literal["verify", "enroll"] = "verify" if user.totp_enabled else "enroll"
    token = secrets.token_urlsafe(32)
    db.add(
        MfaChallenge(
            token_hmac=_challenge_hmac(token),
            user_id=user.id,
            kind=kind,
            created_at=now,
            expires_at=now + MFA_CHALLENGE_TTL,
        )
    )
    db.flush()
    log_event(meta, AuditAction.PASSWORD_OK, user_id=user.id)
    return LoginResult(next="mfa_verify" if kind == "verify" else "mfa_enroll", mfa_token=token)


def _load_challenge(
    db: Session, token: str, kind: str, now: datetime
) -> tuple[MfaChallenge, User]:
    challenge = db.execute(
        select(MfaChallenge)
        .where(MfaChallenge.token_hmac == _challenge_hmac(token))
        .with_for_update()
    ).scalar_one_or_none()
    if (
        challenge is None
        or challenge.kind != kind
        or challenge.used_at is not None
        or challenge.expires_at <= now
        or challenge.attempts >= MFA_MAX_ATTEMPTS
    ):
        raise AuthError("mfa_expired")
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active:
        raise AuthError("mfa_expired")
    return challenge, user


def _fail_attempt(db: Session, challenge: MfaChallenge, user: User, meta: ClientMeta) -> NoReturn:
    challenge.attempts += 1
    db.commit()
    log_event(meta, AuditAction.MFA_FAIL, user_id=user.id, result="fail",
              details={"attempts": challenge.attempts})
    raise AuthError("invalid_mfa_code")


def _consume_backup_code(db: Session, user_id: int, code: str, now: datetime) -> bool:
    normalized = totp.normalize_backup_code(code)
    if normalized is None:
        return False
    row = db.execute(
        select(BackupCode)
        .where(
            BackupCode.user_id == user_id,
            BackupCode.code_hmac == _backup_hmac(user_id, normalized),
            BackupCode.used_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return False
    row.used_at = now
    return True


def issue_backup_codes(db: Session, user_id: int) -> list[str]:
    db.execute(delete(BackupCode).where(BackupCode.user_id == user_id))
    codes = totp.generate_backup_codes()
    for code in codes:
        normalized = totp.normalize_backup_code(code)
        assert normalized is not None
        db.add(BackupCode(user_id=user_id, code_hmac=_backup_hmac(user_id, normalized)))
    return codes


def _decrypt_secret(user: User) -> str | None:
    if user.totp_secret_enc is None:
        return None
    try:
        return keystore.decrypt_str(Purpose.MFA, user.totp_secret_enc, totp_aad(user.id))
    except CryptoError:
        return None


def verify_mfa(
    db: Session, token: str, code: str, meta: ClientMeta, now: datetime
) -> tuple[sessions.NewSession, User]:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.MFA_PER_IP)
    challenge, user = _load_challenge(db, token, "verify", now)
    secret = _decrypt_secret(user)
    step = totp.verify(secret, code, user.totp_last_step, now.timestamp()) if secret else None
    used_backup = False
    if step is not None:
        user.totp_last_step = step
    else:
        used_backup = _consume_backup_code(db, user.id, code, now)
        if not used_backup:
            _fail_attempt(db, challenge, user, meta)
    challenge.used_at = now
    user.last_login_at = now
    new = sessions.create(db, user.id, meta.ip, meta.ua, now)
    if used_backup:
        log_event(meta, AuditAction.BACKUP_CODE_USED, user_id=user.id)
    log_event(meta, AuditAction.LOGIN_OK, user_id=user.id,
              details={"method": "backup_code" if used_backup else "totp"})
    return new, user


def enroll_start(db: Session, token: str, now: datetime) -> EnrollStart:
    _challenge, user = _load_challenge(db, token, "enroll", now)
    if user.totp_enabled:
        raise ConflictError("mfa_already_enabled")
    secret = totp.new_secret()
    user.totp_secret_enc = keystore.encrypt_str(Purpose.MFA, secret, totp_aad(user.id))
    uri = totp.provisioning_uri(secret, user.username)
    return EnrollStart(otpauth_uri=uri, qr_svg_data_uri=totp.qr_data_uri(uri), secret=secret)


def enroll_confirm(
    db: Session, token: str, code: str, meta: ClientMeta, now: datetime
) -> tuple[sessions.NewSession, User, list[str]]:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.MFA_PER_IP)
    challenge, user = _load_challenge(db, token, "enroll", now)
    if user.totp_enabled:
        raise ConflictError("mfa_already_enabled")
    secret = _decrypt_secret(user)
    if secret is None:
        raise AuthError("mfa_expired")
    step = totp.verify(secret, code, None, now.timestamp())
    if step is None:
        _fail_attempt(db, challenge, user, meta)
    user.totp_enabled = True
    user.totp_last_step = step
    codes = issue_backup_codes(db, user.id)
    challenge.used_at = now
    user.last_login_at = now
    new = sessions.create(db, user.id, meta.ip, meta.ua, now)
    log_event(meta, AuditAction.MFA_ENROLLED, user_id=user.id)
    log_event(meta, AuditAction.LOGIN_OK, user_id=user.id, details={"method": "totp_enroll"})
    return new, user, codes


def change_password(
    db: Session, ctx: AuthContext, current: str, new: str, meta: ClientMeta, now: datetime
) -> None:
    user = db.get(User, ctx.user_id, with_for_update=True)
    if user is None:
        raise AuthError("session_expired")
    if not passwords.verify_password(current, user.password_hash):
        log_event(meta, AuditAction.PASSWORD_CHANGE_FAIL, user_id=user.id, result="fail")
        raise ValidationFailed("invalid_current_password")
    history = [
        user.password_hash,
        *db.execute(
            select(PasswordHistory.password_hash)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            .limit(passwords.HISTORY_DEPTH - 1)
        ).scalars(),
    ]
    problems = passwords.policy_problems(new, username=user.username, previous_hashes=history)
    if problems:
        raise ValidationFailed("password_policy", problems=problems)
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash, created_at=now))
    db.flush()
    keep = select(PasswordHistory.id).where(PasswordHistory.user_id == user.id).order_by(
        PasswordHistory.created_at.desc(), PasswordHistory.id.desc()
    ).limit(passwords.HISTORY_DEPTH - 1)
    db.execute(
        delete(PasswordHistory).where(
            PasswordHistory.user_id == user.id, PasswordHistory.id.not_in(keep.scalar_subquery())
        )
    )
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    user.must_change_password = False
    sessions.revoke_all(db, user.id, "password_changed", now, except_id=ctx.session_id)
    log_event(meta, AuditAction.PASSWORD_CHANGED, user_id=user.id)


def logout(db: Session, ctx: AuthContext, meta: ClientMeta, now: datetime) -> None:
    sessions.revoke(db, ctx.session_id, "logout", now)
    log_event(meta, AuditAction.LOGOUT, user_id=ctx.user_id)


def list_sessions(db: Session, ctx: AuthContext) -> list[SessionOut]:
    rows = db.execute(
        select(UserSession)
        .where(UserSession.user_id == ctx.user_id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    ).scalars()
    out: list[SessionOut] = []
    for row in rows:
        ip: str | None = None
        if row.ip_enc is not None:
            try:
                ip = keystore.decrypt_str(Purpose.PII, row.ip_enc, sessions.ip_aad(row.id))
            except CryptoError:
                ip = None
        out.append(
            SessionOut(
                id=row.id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                ua_summary=row.ua_summary,
                ip=ip,
                current=row.id == ctx.session_id,
            )
        )
    return out


def revoke_own_session(
    db: Session, ctx: AuthContext, session_id: uuid.UUID, meta: ClientMeta, now: datetime
) -> None:
    row = db.get(UserSession, session_id)
    if row is None or row.user_id != ctx.user_id:
        raise NotFoundError()
    sessions.revoke(db, session_id, "user_revoked", now)
    log_event(meta, AuditAction.SESSION_REVOKED, user_id=ctx.user_id,
              object_type="session", object_id=session_id)
