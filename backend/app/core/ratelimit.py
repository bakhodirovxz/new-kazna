"""So'rov chastotasini cheklash (Redis, qat'iy oyna).

Redis ishlamasa cheklov vaqtincha O'CHADI (fail-open) va WARNING yoziladi: kesh
tushgani uchun butun tizim to'xtamasligi kerak. Login uchun DB'dagi blok (5 xato →
15 daqiqa) Redis'ga bog'liq emas va baribir ishlaydi.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import redis

from app.core import sysconfig
from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.logging import get_logger

log = get_logger("ugekazna.ratelimit")
RETRY_CLIENT_AFTER = 30.0


@dataclass(frozen=True, slots=True)
class Limit:
    events: int
    window: int




def _per(key: str, window: int) -> Limit:
    return Limit(events=int(sysconfig.value(key)), window=window)


def login_per_ip() -> Limit:
    return _per("ratelimit.login_per_min", 60)


def mfa_per_ip() -> Limit:
    return _per("ratelimit.mfa_per_min", 60)


def api_per_user() -> Limit:
    return _per("ratelimit.api_per_min", 60)


def password_change_per_user() -> Limit:
    return _per("ratelimit.password_change_per_15min", 900)


# Task 12 fix r1: POST /audit/verify to'liq jadval bo'yicha HMAC skanerlash — arzon amal
# emas, shuning uchun boshqa endpointlarga qaraganda ancha qattiqroq cheklanadi: har
# foydalanuvchi UCHUN va, DoS'dan himoya sifatida, BUTUN tizim uchun ham (identity "global").
AUDIT_VERIFY_PER_USER = Limit(events=3, window=600)
AUDIT_VERIFY_GLOBAL = Limit(events=10, window=3600)
STEP_UP_PER_USER = Limit(events=5, window=900)

_client_override: redis.Redis | None = None
_lock = threading.Lock()
_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client_override is not None:
        return _client_override
    with _lock:
        if _client is None:
            _client = redis.Redis.from_url(
                get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1
            )
        return _client


_last_failure = 0.0


def check(scope: str, identity: str, limit: Limit) -> int:
    """Hisoblagichni oshiradi, qolgan urinishlar sonini qaytaradi; oshsa RateLimitedError."""
    global _last_failure
    key = f"rl:{scope}:{identity}"
    if _client_override is None and time.monotonic() - _last_failure < RETRY_CLIENT_AFTER:
        return limit.events
    try:
        pipe = _get_client().pipeline()
        pipe.incr(key)
        pipe.expire(key, limit.window, nx=True)
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
    except redis.RedisError as exc:
        _last_failure = time.monotonic()
        log.warning("ratelimit_unavailable", error=type(exc).__name__)
        return limit.events
    if int(count) > limit.events:
        raise RateLimitedError(retry_after=max(1, int(ttl)))
    return limit.events - int(count)


def reset(scope: str, identity: str) -> None:
    try:
        _get_client().delete(f"rl:{scope}:{identity}")
    except redis.RedisError:
        log.warning("ratelimit_reset_failed")


def ping() -> bool:
    try:
        return bool(_get_client().ping())
    except redis.RedisError:
        return False
