"""TOTP (RFC 6238) va bir martalik zaxira kodlar."""

from __future__ import annotations

import hmac
import re
import secrets

import pyotp
import segno

ISSUER = "UGEKAZNA"
STEP_SECONDS = 30
DIGITS = 6
BACKUP_CODE_COUNT = 10
_BACKUP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # I, L, O, 0, 1 yo'q
# 12 belgi, 31 belgili alifbo -> ~59 bit entropiya (loyihada belgilangan >=50 bit)
_BACKUP_RE = re.compile(r"^(?:[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}|[A-Z0-9]{12})$")


def new_secret() -> str:
    return str(pyotp.random_base32(length=32))


def _totp(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS)


def provisioning_uri(secret: str, username: str) -> str:
    return str(_totp(secret).provisioning_uri(name=username, issuer_name=ISSUER))


def qr_data_uri(uri: str) -> str:
    return str(segno.make(uri, error="m").svg_data_uri(scale=5, border=2))


def verify(secret: str, code: str, last_step: int | None, now: float) -> int | None:
    """Mos kelgan qadam raqamini qaytaradi. `last_step` va undan oldingilari qabul qilinmaydi."""
    code = code.strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    otp = _totp(secret)
    current = int(now) // STEP_SECONDS
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(str(otp.at(step * STEP_SECONDS)), code):
            return step
    return None


def generate_backup_codes() -> list[str]:
    codes: set[str] = set()
    while len(codes) < BACKUP_CODE_COUNT:
        raw = "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(12))
        codes.add(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return sorted(codes)


def normalize_backup_code(code: str) -> str | None:
    cleaned = code.strip().upper().replace(" ", "")
    if not _BACKUP_RE.match(cleaned):
        return None
    return cleaned.replace("-", "")
