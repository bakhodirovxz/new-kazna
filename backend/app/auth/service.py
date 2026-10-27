"""Autentifikatsiya oqimlari (spec 3.1): parol → 2FA challenge → sessiya."""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, NoReturn

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth import passwords, sessions, totp
from app.auth.context import AuthContext
from app.auth.models import BackupCode, MfaChallenge, PasswordHistory, User, UserSession
from app.auth.schemas import SessionOut
from app.core import keystore, ratelimit, sysconfig
from app.core.crypto import CryptoError, Purpose, keyed_hash
from app.core.errors import AuthError, ConflictError, NotFoundError, ValidationFailed
from app.core.request_meta import ClientMeta

MFA_CHALLENGE_TTL = timedelta(minutes=5)
MFA_MAX_ATTEMPTS = 5
_USERNAME_HINT_RE = re.compile(r"^[a-z0-9._-]{2}$")


@dataclass(frozen=True, slots=True)
class LoginResult:
    next: Literal["mfa_verify", "mfa_enroll"]
    mfa_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class EnrollStart:
    otpauth_uri: str = field(repr=False)
    qr_svg_data_uri: str
    secret: str = field(repr=False)


def normalize_username(raw: str) -> str:
    return unicodedata.normalize("NFKC", raw).strip().lower()


def totp_aad(user_id: int) -> str:
    return f"core.users.totp_secret_enc:{user_id}"


def _challenge_hmac(token: str) -> bytes:
    return keyed_hash(keystore.pepper(), "mfa", token)


def _backup_hmac(user_id: int, normalized: str) -> bytes:
    return keyed_hash(keystore.pepper(), "backup", f"{user_id}:{normalized}")


def _pending_secret_aad(token_hmac: bytes) -> str:
    """M7: kutilayotgan TOTP siri konkret challenge'ga bog'lanadi, foydalanuvchiga emas —
    ikki parallel enroll challenge bir-birining sirini almashtira olmasligi uchun."""
    return f"core.mfa_challenges.pending_secret_enc:{token_hmac.hex()}"


def _unknown_user_audit_details(normalized: str) -> dict[str, Any]:
    """M5: noma'lum foydalanuvchi urinishida audit jurnaliga to'liq login yozilmaydi —
    faqat uzunlik, barqaror HMAC "fingerprint" va (xavfsiz alifbodan bo'lsa) 2 belgili maslahat."""
    details: dict[str, Any] = {
        "username_len": len(normalized),
        "username_fp": keyed_hash(keystore.pepper(), "username", normalized).hex()[:16],
        "reason": "unknown_user",
    }
    hint = normalized[:2]
    if _USERNAME_HINT_RE.fullmatch(hint):
        details["username_hint"] = f"{hint}…"
    return details


def login(
    db: Session, username: str, password: str, meta: ClientMeta, now: datetime
) -> LoginResult:
    ratelimit.check("login_ip", meta.ip or "unknown", ratelimit.login_per_ip())
    uname = normalize_username(username)
    # I1: qator qulfi bilan o'qiladi — parallel noto'g'ri urinishlar (bir xil foydalanuvchi)
    # ketma-ketlashadi, aks holda `failed_logins += 1` yo'qolgan yangilanishga olib kelardi.
    user = db.execute(
        select(User).where(User.username == uname).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        passwords.dummy_verify(password)
        log_event(meta, AuditAction.LOGIN_FAIL, user_id=None, result="fail",
                  details=_unknown_user_audit_details(uname))
        raise AuthError("invalid_credentials")

    password_ok = passwords.verify_password(password, user.password_hash)
    locked = user.locked_until is not None and user.locked_until > now
    if not user.is_active or locked or not password_ok:
        reason = "inactive" if not user.is_active else "locked" if locked else "bad_password"
        if reason == "bad_password":
            user.failed_logins += 1
            if user.failed_logins >= int(sysconfig.value("security.login_max_failures")):
                user.locked_until = now + _lockout()
                user.failed_logins = 0
                reason = "locked_now"
            db.commit()  # so'rov rollback bo'lsa ham hisoblagich saqlanadi
        log_event(meta, AuditAction.LOGIN_FAIL, user_id=user.id, result="fail",
                  details={"reason": reason})
        raise AuthError("invalid_credentials")

    # I3: `failed_logins` endi FAQAT to'liq (ikkinchi faktorli) muvaffaqiyatdan keyin
    # nolga tushadi — parol qadami hali to'liq autentifikatsiya emas.
    user.locked_until = None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    kind: Literal["verify", "enroll"] = "verify" if user.totp_enabled else "enroll"
    token = secrets.token_urlsafe(32)
    # I3: yangi challenge ochilganda foydalanuvchining boshqa ochiq challenge'lari
    # o'chiriladi (bir vaqtda faqat bitta challenge tirik bo'lsin). Kutilayotgan enroll
    # siri ham tozalanadi (fix r2 — o'lik challenge'da shifrlangan sir qolib ketmasin).
    db.execute(
        update(MfaChallenge)
        .where(MfaChallenge.user_id == user.id, MfaChallenge.used_at.is_(None))
        .values(used_at=now, pending_secret_enc=None)
    )
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
    """R2-1: FOYDALANUVCHI qatori HAR DOIM challenge qatoridan OLDIN qulflanadi — `login()`
    va `change_password()` ham shu tartibda ishlaydi (avval user, keyin challenge'larni
    bekor qiluvchi UPDATE). Teskari tartib (avval challenge, keyin user, eski koddagidek)
    lock-order inversion va Postgres DeadlockDetected'ga olib kelardi (parallel `login()`
    va `verify_mfa()` bir xil foydalanuvchiga qarshi ishlaganda).

    Shu sabab qulfsiz egasini bilib olib, avval FOYDALANUVCHINI qulflaymiz, so'ng
    challenge'ni qulflab HAMMA narsani QAYTA tekshiramiz — qulfsiz o'qishdan keyin holat
    o'zgargan (masalan boshqa tranzaksiya uni bekor qilgan) bo'lishi mumkin.
    """
    token_hmac = _challenge_hmac(token)
    owner_id = db.execute(
        select(MfaChallenge.user_id).where(MfaChallenge.token_hmac == token_hmac)
    ).scalar_one_or_none()
    if owner_id is None:
        raise AuthError("mfa_expired")
    # I2: foydalanuvchi qatori qulflanadi — parallel `verify`/`enroll` urinishlari
    # (masalan, bir xil TOTP kodi bilan) `totp_last_step`/`failed_logins` ustida
    # ketma-ketlashadi, aks holda ikkalasi ham "muvaffaqiyatli" bo'lib qolishi mumkin edi.
    user = db.get(User, owner_id, with_for_update=True, populate_existing=True)
    if user is None or not user.is_active:
        raise AuthError("mfa_expired")
    # I3: bloklangan foydalanuvchining ochiq challenge'i ham, hatto to'g'ri kod bilan ham
    # ishlamasligi kerak.
    if user.locked_until is not None and user.locked_until > now:
        raise AuthError("mfa_expired")
    challenge = db.execute(
        select(MfaChallenge).where(MfaChallenge.token_hmac == token_hmac).with_for_update()
    ).scalar_one_or_none()
    if (
        challenge is None
        or challenge.user_id != owner_id
        or challenge.kind != kind
        or challenge.used_at is not None
        or challenge.expires_at <= now
        or challenge.attempts >= MFA_MAX_ATTEMPTS
    ):
        raise AuthError("mfa_expired")
    return challenge, user


def _fail_attempt(
    db: Session, challenge: MfaChallenge, user: User, meta: ClientMeta, now: datetime
) -> NoReturn:
    """I3: noto'g'ri 2FA kodlari ham parol xatolari bilan bitta hisoblagichga qo'shiladi —
    aks holda cheksiz TOTP-brute-force turli yangi challenge'lar orqali mumkin bo'lardi."""
    challenge.attempts += 1
    user.failed_logins += 1
    locked_now = False
    if user.failed_logins >= int(sysconfig.value("security.login_max_failures")):
        user.locked_until = now + _lockout()
        user.failed_logins = 0
        locked_now = True
    db.commit()
    log_event(meta, AuditAction.MFA_FAIL, user_id=user.id, result="fail",
              details={"attempts": challenge.attempts, "locked": locked_now})
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


def _lockout() -> timedelta:
    return timedelta(minutes=int(sysconfig.value("security.login_lockout_minutes")))


def decrypt_totp_secret(user: User) -> str | None:
    if user.totp_secret_enc is None:
        return None
    try:
        return keystore.decrypt_str(Purpose.MFA, user.totp_secret_enc, totp_aad(user.id))
    except CryptoError:
        return None


def verify_mfa(
    db: Session, token: str, code: str, meta: ClientMeta, now: datetime
) -> tuple[sessions.NewSession, User]:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.mfa_per_ip())
    challenge, user = _load_challenge(db, token, "verify", now)
    secret = decrypt_totp_secret(user)
    step = totp.verify(secret, code, user.totp_last_step, now.timestamp()) if secret else None
    used_backup = False
    if step is not None:
        user.totp_last_step = step
    else:
        used_backup = _consume_backup_code(db, user.id, code, now)
        if not used_backup:
            _fail_attempt(db, challenge, user, meta, now)
    # I3: to'liq (ikkinchi faktorli) muvaffaqiyat — endi hisoblagich va blok tozalanadi.
    user.failed_logins = 0
    user.locked_until = None
    challenge.used_at = now
    user.last_login_at = now
    new = sessions.create(db, user.id, meta.ip, meta.ua, now)
    if used_backup:
        log_event(meta, AuditAction.BACKUP_CODE_USED, user_id=user.id)
    log_event(meta, AuditAction.LOGIN_OK, user_id=user.id,
              details={"method": "backup_code" if used_backup else "totp"})
    return new, user


def enroll_start(db: Session, token: str, meta: ClientMeta, now: datetime) -> EnrollStart:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.mfa_per_ip())  # M12
    challenge, user = _load_challenge(db, token, "enroll", now)
    if user.totp_enabled:
        raise ConflictError("mfa_already_enabled")
    secret = totp.new_secret()
    # M7: sir foydalanuvchiga emas, shu challenge'ga bog'lab saqlanadi (AAD challenge
    # token_hmac'idan chiqariladi) — parallel enroll challenge'lar bir-birining sirini
    # almashtira olmaydi.
    challenge.pending_secret_enc = keystore.encrypt_str(
        Purpose.MFA, secret, _pending_secret_aad(challenge.token_hmac)
    )
    uri = totp.provisioning_uri(secret, user.username)
    return EnrollStart(otpauth_uri=uri, qr_svg_data_uri=totp.qr_data_uri(uri), secret=secret)


def enroll_confirm(
    db: Session, token: str, code: str, meta: ClientMeta, now: datetime
) -> tuple[sessions.NewSession, User, list[str]]:
    ratelimit.check("mfa_ip", meta.ip or "unknown", ratelimit.mfa_per_ip())
    challenge, user = _load_challenge(db, token, "enroll", now)
    if user.totp_enabled:
        raise ConflictError("mfa_already_enabled")
    if challenge.pending_secret_enc is None:
        raise AuthError("mfa_expired")
    try:
        secret = keystore.decrypt_str(
            Purpose.MFA, challenge.pending_secret_enc, _pending_secret_aad(challenge.token_hmac)
        )
    except CryptoError as exc:
        raise AuthError("mfa_expired") from exc
    step = totp.verify(secret, code, None, now.timestamp())
    if step is None:
        _fail_attempt(db, challenge, user, meta, now)
    # Faqat tasdiqlangandan keyin doimiy joyga (foydalanuvchi AAD'i bilan) ko'chiriladi.
    user.totp_secret_enc = keystore.encrypt_str(Purpose.MFA, secret, totp_aad(user.id))
    user.totp_enabled = True
    user.totp_last_step = step
    user.failed_logins = 0
    user.locked_until = None
    codes = issue_backup_codes(db, user.id)
    challenge.used_at = now
    challenge.pending_secret_enc = None  # fix r2: vaqtinchalik shifrlangan sir endi kerak emas
    user.last_login_at = now
    new = sessions.create(db, user.id, meta.ip, meta.ua, now)
    log_event(meta, AuditAction.MFA_ENROLLED, user_id=user.id)
    log_event(meta, AuditAction.LOGIN_OK, user_id=user.id, details={"method": "totp_enroll"})
    return new, user, codes


def change_password(
    db: Session, ctx: AuthContext, current: str, new: str, meta: ClientMeta, now: datetime
) -> sessions.NewSession:
    # I4: shifrlangan-parol "oracle"ni cheklaydigan maxsus limit — tekshiruvdan OLDIN.
    ratelimit.check("password_change_user", str(ctx.user_id), ratelimit.password_change_per_user())
    user = db.get(User, ctx.user_id, with_for_update=True)
    if user is None:
        raise AuthError("session_expired")
    if not passwords.verify_password(current, user.password_hash):
        # I4: noto'g'ri joriy parol ham umumiy hisoblagichga qo'shiladi; chegaraga
        # yetganda hisob bloklanadi VA barcha sessiyalar bekor qilinadi (o'g'irlangan
        # sessiya orqali "oracle" bilan parolni taxmin qilishning oldini olish uchun).
        user.failed_logins += 1
        locked_now = False
        if user.failed_logins >= int(sysconfig.value("security.login_max_failures")):
            user.locked_until = now + _lockout()
            user.failed_logins = 0
            locked_now = True
            sessions.revoke_all(db, user.id, "password_change_lockout", now)
        db.commit()
        log_event(meta, AuditAction.PASSWORD_CHANGE_FAIL, user_id=user.id, result="fail",
                  details={"locked": locked_now})
        raise ValidationFailed("invalid_current_password")
    history = [
        user.password_hash,
        *db.execute(
            select(PasswordHistory.password_hash)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            .limit(passwords.history_depth() - 1)
        ).scalars(),
    ]
    problems = passwords.policy_problems(new, username=user.username, previous_hashes=history)
    if problems:
        raise ValidationFailed("password_policy", problems=problems)
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash, created_at=now))
    db.flush()
    keep = select(PasswordHistory.id).where(PasswordHistory.user_id == user.id).order_by(
        PasswordHistory.created_at.desc(), PasswordHistory.id.desc()
    ).limit(passwords.history_depth() - 1)
    db.execute(
        delete(PasswordHistory).where(
            PasswordHistory.user_id == user.id, PasswordHistory.id.not_in(keep.scalar_subquery())
        )
    )
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    user.must_change_password = False
    # M8: parol o'zgarganda ochiq 2FA challenge'lari ham, JORIY sessiya ham bekor
    # qilinadi — yangi sessiya chiqariladi (router yangi cookie'larni o'rnatadi). Kutilayotgan
    # enroll siri ham tozalanadi (fix r2).
    db.execute(
        update(MfaChallenge)
        .where(MfaChallenge.user_id == user.id, MfaChallenge.used_at.is_(None))
        .values(used_at=now, pending_secret_enc=None)
    )
    # fix r2 (kam xarajatli): yangi sessiya eskisining absolyut muddatidan
    # UZOQROQ bo'lmasin — parol almashtirish "abadiy" sessiyaga aylanmasin.
    old_session = db.get(UserSession, ctx.session_id)
    old_absolute = old_session.absolute_expires_at if old_session is not None else None
    sessions.revoke_all(db, user.id, "password_changed", now)
    new_session = sessions.create(
        db, user.id, meta.ip, meta.ua, now, absolute_expires_at=old_absolute
    )
    log_event(meta, AuditAction.PASSWORD_CHANGED, user_id=user.id)
    return new_session


def logout(
    db: Session, session_id: uuid.UUID, user_id: int, meta: ClientMeta, now: datetime
) -> None:
    sessions.revoke(db, session_id, "logout", now)
    log_event(meta, AuditAction.LOGOUT, user_id=user_id)


def list_sessions(db: Session, ctx: AuthContext, now: datetime) -> list[SessionOut]:
    # M9: faqat bekor qilinmagan VA hali idle/absolyut muddati tugamagan sessiyalar.
    rows = db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == ctx.user_id,
            UserSession.revoked_at.is_(None),
            UserSession.idle_expires_at > now,
            UserSession.absolute_expires_at > now,
        )
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
