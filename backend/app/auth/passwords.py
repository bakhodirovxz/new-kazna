"""Parollar: Argon2id va parol siyosati (spec 3.1)."""

from __future__ import annotations

import gzip
import secrets
import string
from collections.abc import Sequence
from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

STANDARD_PARAMS = (3, 64 * 1024, 4)  # time_cost, memory_cost (KiB), parallelism
FAST_TEST_PARAMS = (1, 8 * 1024, 1)
MIN_LENGTH = 12
HISTORY_DEPTH = 5
CONTEXT_WORDS = ("ugekazna", "gidroenergo", "password", "qwerty", "admin")
_TEMP_ALPHABET = string.ascii_letters + string.digits + "-_!@#%+="


def _make_hasher() -> PasswordHasher:
    fast = get_settings().argon2_profile == "fast_test"
    t, m, p = FAST_TEST_PARAMS if fast else STANDARD_PARAMS
    return PasswordHasher(time_cost=t, memory_cost=m, parallelism=p, hash_len=32, salt_len=16)


_hasher = _make_hasher()
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def dummy_verify(password: str) -> None:
    """Foydalanuvchi topilmaganda ham bir xil vaqt sarflaydi (timing attack'dan himoya)."""
    verify_password(password, _DUMMY_HASH)


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    raw = resources.files("app.auth.data").joinpath("common-passwords.txt.gz").read_bytes()
    lines = gzip.decompress(raw).decode("utf-8", "ignore").splitlines()
    return frozenset(line.strip().casefold() for line in lines if line.strip())


def _classes(password: str) -> int:
    return sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )


def policy_problems(
    password: str, *, username: str, previous_hashes: Sequence[str] = ()
) -> list[str]:
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append("password_too_short")
    if _classes(password) < 3:
        problems.append("password_too_simple")
    folded = password.casefold()
    if len(username) >= 3 and username.casefold() in folded:
        problems.append("password_contains_username")
    if folded in _common_passwords() or any(w in folded for w in CONTEXT_WORDS):
        problems.append("password_common")
    if not problems and any(verify_password(password, h) for h in previous_hashes):
        problems.append("password_reused")
    return problems


def generate_temporary_password(length: int = 16) -> str:
    while True:
        candidate = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if not policy_problems(candidate, username=""):
            return candidate
