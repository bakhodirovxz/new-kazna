"""DEK'lar bazada KEK bilan o'ralgan holda turadi; jarayonda 60 s keshlanadi."""

from __future__ import annotations

import threading
import time
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.crypto import CryptoError, Keyring, Purpose, new_dek, unwrap_key, wrap_key
from app.core.db import get_engine

CACHE_TTL_SECONDS = 60.0
_ADVISORY_LOCK_KEY = "ugk_key_rotate"
_lock = threading.Lock()
_cache: tuple[Keyring, float] | None = None


def _take_key_lock(conn: Connection) -> None:
    """Kalit mutatsiyalarini (ensure/rotate/rewrap) o'zaro serializatsiya qiladi."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": _ADVISORY_LOCK_KEY})


def _verify_kek(conn: Connection, kek: bytes, purpose: Purpose | None = None) -> None:
    """Mavjud bitta yozuvni ochib, berilgan KEK to'g'riligini tasdiqlaydi.

    Mos yozuv topilmasa (masalan, bazada hali hech narsa yo'q) — jim tasdiqlanadi.
    """
    query = "SELECT wrapped_key FROM core.crypto_keys WHERE status <> 'retired'"
    params: dict[str, str] = {}
    if purpose is not None:
        query += " AND purpose = :p"
        params["p"] = purpose.value
    row = conn.execute(text(query + " LIMIT 1"), params).scalar()
    if row is not None:
        unwrap_key(kek, bytes(row))


def ensure_keys(conn: Connection, kek: bytes) -> None:
    """Har maqsad uchun kalit bo'lmasa, 1-versiyani yaratadi (idempotent)."""
    _take_key_lock(conn)
    _verify_kek(conn, kek)
    for purpose in Purpose:
        conn.execute(
            text(
                "INSERT INTO core.crypto_keys (purpose, version, wrapped_key, status) "
                "SELECT :p, 1, :w, 'active' "
                "WHERE NOT EXISTS (SELECT 1 FROM core.crypto_keys WHERE purpose = :p) "
                "ON CONFLICT DO NOTHING"
            ),
            {"p": purpose.value, "w": wrap_key(kek, new_dek())},
        )


def load_keyring(conn: Connection, kek: bytes) -> Keyring:
    rows = conn.execute(
        text(
            "SELECT purpose, version, wrapped_key, status FROM core.crypto_keys "
            "WHERE status IN ('active', 'decrypt_only')"
        )
    ).all()
    keys: dict[tuple[str, int], bytes] = {}
    active: dict[str, int] = {}
    for purpose, version, wrapped, status in rows:
        keys[(purpose, version)] = unwrap_key(kek, bytes(wrapped))
        if status == "active":
            active[purpose] = version
    missing = [p.value for p in Purpose if p.value not in active]
    if missing:
        raise CryptoError("no_active_key", detail=f"faol kalit yo'q: {','.join(missing)}")
    return Keyring(keys=keys, active=active)


def get_keyring() -> Keyring:
    global _cache
    now = time.monotonic()
    with _lock:
        if _cache is not None and now - _cache[1] < CACHE_TTL_SECONDS:
            return _cache[0]
        kek = get_settings().key_bytes("master_kek")
        with get_engine("app").connect() as conn:
            ring = load_keyring(conn, kek)
        _cache = (ring, now)
        return ring


def invalidate_keyring() -> None:
    global _cache
    with _lock:
        _cache = None


def rotate(conn: Connection, kek: bytes, purpose: Purpose) -> int:
    """Yangi faol versiya; eskisi faqat ochish uchun qoladi."""
    _take_key_lock(conn)
    _verify_kek(conn, kek, purpose)
    current = conn.execute(
        text("SELECT coalesce(max(version), 0) FROM core.crypto_keys WHERE purpose = :p"),
        {"p": purpose.value},
    ).scalar_one()
    conn.execute(
        text(
            "UPDATE core.crypto_keys SET status = 'decrypt_only' "
            "WHERE purpose = :p AND status = 'active'"
        ),
        {"p": purpose.value},
    )
    new_version = int(current) + 1
    conn.execute(
        text(
            "INSERT INTO core.crypto_keys (purpose, version, wrapped_key, status) "
            "VALUES (:p, :v, :w, 'active')"
        ),
        {"p": purpose.value, "v": new_version, "w": wrap_key(kek, new_dek())},
    )
    return new_version


def rewrap_all(conn: Connection, old_kek: bytes, new_kek: bytes) -> int:
    """KEK rotatsiyasi: barcha tirik DEK'larni yangi KEK bilan qayta o'raydi.

    Operator amali — `ugk_migrator` (jadval egasi) sifatida bajariladi: `ugk_app`'ning
    `wrapped_key` ustunini yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5).
    """
    _take_key_lock(conn)
    rows = conn.execute(
        text("SELECT id, wrapped_key FROM core.crypto_keys WHERE status <> 'retired' FOR UPDATE")
    ).all()
    for key_id, wrapped in rows:
        dek = unwrap_key(old_kek, bytes(wrapped))
        conn.execute(
            text("UPDATE core.crypto_keys SET wrapped_key = :w WHERE id = :id"),
            {"w": wrap_key(new_kek, dek), "id": key_id},
        )
    return len(rows)


def encrypt(purpose: Purpose, plaintext: bytes, aad: str) -> bytes:
    return get_keyring().encrypt(purpose, plaintext, aad)


def decrypt(purpose: Purpose, blob: bytes, aad: str) -> bytes:
    try:
        return get_keyring().decrypt(purpose, blob, aad)
    except CryptoError as exc:
        if exc.reason != "unknown_key_version":
            raise
    # Boshqa worker kalitni aylantirgan bo'lishi mumkin — keshni yangilab qayta urinamiz.
    invalidate_keyring()
    return get_keyring().decrypt(purpose, blob, aad)


def encrypt_str(purpose: Purpose, value: str, aad: str) -> bytes:
    return encrypt(purpose, value.encode("utf-8"), aad)


def decrypt_str(purpose: Purpose, blob: bytes, aad: str) -> str:
    return decrypt(purpose, bytes(blob), aad).decode("utf-8")


@lru_cache(maxsize=1)
def pepper() -> bytes:
    """Sessiya/challenge tokenlari va zaxira kodlar HMAC'i uchun kalit."""
    return get_settings().key_bytes("session_pepper")
