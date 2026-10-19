"""Redis kesh va HTTP ETag (spec 6.2).

Kalit: ugk:v{data_version}:{endpoint}:{scope_hash}:{filters_hash}. data_version — aktiv build;
publish/rollback'da o'zgaradi, eski kalitlar ishlatilmay qoladi (TTL 1 soat). scope_hash
foydalanuvchi filial doirasidan — boshqa doira keshi hech qachon qaytmaydi. Single-flight:
`SET NX PX 5000` lock. Redis ishlamasa — fail-open (to'g'ridan-to'g'ri hisoblanadi).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Annotated, Any

import redis
from fastapi import Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, Ctx
from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import get_logger

CACHE_TTL = 3600
LOCK_TTL_MS = 5000
WAIT_STEP = 0.05
RETRY_CLIENT_AFTER = 30.0
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end"

log = get_logger("ugekazna.cache")
_client_override: redis.Redis | None = None
_client: redis.Redis | None = None
_lock = threading.Lock()
_last_failure = 0.0


def _get_client() -> redis.Redis | None:
    global _client
    if _client_override is not None:
        return _client_override
    if time.monotonic() - _last_failure < RETRY_CLIENT_AFTER:
        return None
    with _lock:
        if _client is None:
            _client = redis.Redis.from_url(
                get_settings().redis_url, socket_timeout=0.5, socket_connect_timeout=0.5
            )
        return _client


def _failed(exc: Exception) -> None:
    global _last_failure
    _last_failure = time.monotonic()
    log.warning("cache_unavailable", error=type(exc).__name__)


def current_version(db: Session) -> int:
    value = db.execute(
        text("SELECT coalesce(active_build_id, 0) FROM core.data_version WHERE id = 1")
    ).scalar_one_or_none()
    return int(value or 0)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def scope_hash(branch_ids: frozenset[int] | None) -> str:
    return _digest("all" if branch_ids is None else ",".join(str(b) for b in sorted(branch_ids)))


def filters_hash(filters: Mapping[str, Any]) -> str:
    return _digest(json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str,
                              ensure_ascii=False))


def cache_key(version: int, endpoint: str, scope: str, filters: str) -> str:
    return f"ugk:v{version}:{endpoint}:{scope}:{filters}"


def etag_for(version: int, endpoint: str, scope: str, filters: str) -> str:
    digest = hashlib.sha256(f"{version}|{endpoint}|{scope}|{filters}".encode()).hexdigest()
    return f'"{digest[:32]}"'


def render(payload: Any) -> bytes:
    return json.dumps(jsonable_encoder(payload), ensure_ascii=False,
                      separators=(",", ":")).encode()


def _release(client: redis.Redis, lock_key: str, token: str) -> None:
    try:
        client.eval(_RELEASE, 1, lock_key, token)
    except redis.RedisError as exc:
        _failed(exc)


def cached_body(
    db: Session,
    *,
    endpoint: str,
    scope: str,
    filters: Mapping[str, Any],
    loader: Callable[[], Any],
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bytes, int]:
    """(JSON baytlar, data_version). Loader faqat kesh bo'sh bo'lsa chaqiriladi."""
    version = current_version(db)
    key = cache_key(version, endpoint, scope, filters_hash(filters))
    client = _get_client()
    if client is None:
        return render(loader()), version
    lock_key = f"{key}:lock"
    token = uuid.uuid4().hex
    try:
        hit = client.get(key)
        if isinstance(hit, bytes):
            return hit, version
        owner = bool(client.set(lock_key, token, nx=True, px=LOCK_TTL_MS))
    except redis.RedisError as exc:
        _failed(exc)
        return render(loader()), version
    if not owner:
        deadline = time.monotonic() + LOCK_TTL_MS / 1000
        while time.monotonic() < deadline:
            sleep(WAIT_STEP)
            try:
                hit = client.get(key)
            except redis.RedisError as exc:
                _failed(exc)
                break
            if isinstance(hit, bytes):
                return hit, version
        return render(loader()), version
    try:
        body = render(loader())
        # Hisoblash paytida publish bo'lgan bo'lsa, yangi ma'lumot eski versiya kaliti
        # ostida saqlanib qolmasin (rollback'dan keyin noto'g'ri javob bo'lardi).
        if current_version(db) == version:
            try:
                client.set(key, body, ex=CACHE_TTL)
            except redis.RedisError as exc:
                _failed(exc)
        return body, version
    finally:
        _release(client, lock_key, token)


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    candidates = {part.strip().removeprefix("W/") for part in header.split(",")}
    return "*" in candidates or etag in candidates


class ResponseCache:
    def __init__(self, request: Request, ctx: AuthContext, db: Session) -> None:
        self.request = request
        self.ctx = ctx
        self.db = db

    def respond(self, endpoint: str, filters: Mapping[str, Any],
                loader: Callable[[], Any]) -> Response:
        scope = scope_hash(self.ctx.branch_ids)
        fhash = filters_hash(filters)
        etag = etag_for(current_version(self.db), endpoint, scope, fhash)
        # SecurityHeadersMiddleware setdefault ishlatadi — bu yerdagi qiymat ustun.
        headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Cookie"}
        if _etag_matches(self.request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        body, version = cached_body(self.db, endpoint=endpoint, scope=scope, filters=filters,
                                    loader=loader)
        headers["ETag"] = etag_for(version, endpoint, scope, fhash)
        return Response(content=body, media_type="application/json", headers=headers)


def get_cache(
    request: Request, ctx: Ctx, db: Annotated[Session, Depends(get_db)]
) -> ResponseCache:
    return ResponseCache(request, ctx, db)


Cache = Annotated[ResponseCache, Depends(get_cache)]
