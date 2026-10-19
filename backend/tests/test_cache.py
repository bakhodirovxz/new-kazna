import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.core import cache
from app.core.cache import (
    Cache,
    cache_key,
    cached_body,
    current_version,
    etag_for,
    filters_hash,
    scope_hash,
)
from app.core.config import get_settings
from app.core.db import new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    client = redis.Redis.from_url(get_settings().redis_url)
    for key in client.scan_iter("ugk:*"):
        client.delete(key)
    yield


def _counting(result: Any = None, delay: float = 0.0) -> tuple[Callable[[], Any], list[int]]:
    calls = [0]
    guard = threading.Lock()

    def loader() -> Any:
        with guard:
            calls[0] += 1
        if delay:
            time.sleep(delay)
        return result if result is not None else {"value": 42}

    return loader, calls


def current_version_now() -> int:
    with new_session() as db:
        return current_version(db)


def _publish_new_build() -> int:
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, None)
        builds.mark_ready(conn, build_id)
        builds.publish(conn, build_id, keep=3)
    return build_id


def test_key_and_hash_formats() -> None:
    assert cache_key(5, "meta.branches", "abc", "def") == "ugk:v5:meta.branches:abc:def"
    assert scope_hash(None) != scope_hash(frozenset({3}))
    assert scope_hash(frozenset({3, 7})) == scope_hash(frozenset({7, 3}))
    assert filters_hash({"a": 1, "b": 2}) == filters_hash({"b": 2, "a": 1})
    assert filters_hash({"a": 1}) != filters_hash({"a": 2})


def test_second_call_hits_cache() -> None:
    loader, calls = _counting()
    with new_session() as db:
        first, _ = cached_body(db, endpoint="t.hit", scope="s", filters={}, loader=loader)
        second, _ = cached_body(db, endpoint="t.hit", scope="s", filters={}, loader=loader)
    assert first == second == b'{"value":42}'
    assert calls[0] == 1


def test_scope_and_filters_are_isolated() -> None:
    loader, calls = _counting()
    with new_session() as db:
        cached_body(db, endpoint="t.iso", scope="s1", filters={"a": 1}, loader=loader)
        cached_body(db, endpoint="t.iso", scope="s2", filters={"a": 1}, loader=loader)
        cached_body(db, endpoint="t.iso", scope="s1", filters={"a": 2}, loader=loader)
    assert calls[0] == 3


def test_new_data_version_uses_new_key() -> None:
    loader, calls = _counting()
    with new_session() as db:
        _, v1 = cached_body(db, endpoint="t.ver", scope="s", filters={}, loader=loader)
    new_build = _publish_new_build()
    with new_session() as db:
        _, v2 = cached_body(db, endpoint="t.ver", scope="s", filters={}, loader=loader)
        assert current_version(db) == new_build
    assert v2 == new_build != v1
    assert calls[0] == 2


def test_single_flight_computes_once() -> None:
    loader, calls = _counting(delay=0.3)
    bodies: list[bytes] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with new_session() as db:
                body, _ = cached_body(db, endpoint="t.sf", scope="s", filters={}, loader=loader)
                bodies.append(body)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert calls[0] == 1
    assert len(set(bodies)) == 1 and len(bodies) == 5


def test_redis_down_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "_last_failure", 0.0)
    dead = redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.2, socket_connect_timeout=0.2)
    monkeypatch.setattr(cache, "_client_override", dead)
    loader, calls = _counting()
    with new_session() as db:
        for _ in range(2):
            body, _ = cached_body(db, endpoint="t.down", scope="s", filters={}, loader=loader)
            assert body == b'{"value":42}'
    assert calls[0] == 2


def test_version_change_during_compute_is_not_cached() -> None:
    client = redis.Redis.from_url(get_settings().redis_url)

    def publishing_loader() -> dict[str, int]:
        _publish_new_build()  # publish aynan hisoblash paytida
        return {"stale": 1}

    with new_session() as db:
        _, version = cached_body(db, endpoint="t.race", scope="s", filters={},
                                 loader=publishing_loader)
    assert client.get(cache_key(version, "t.race", "s", filters_hash({}))) is None


def _app() -> FastAPI:
    app = create_app()

    @app.get("/api/v1/_t/cached")
    def cached(cache_dep: Cache) -> Response:
        return cache_dep.respond("t.cached", {"x": 1}, lambda: {"ok": True})

    return app


def test_etag_304_and_headers(make_user: Callable[..., SeedUser]) -> None:
    with TestClient(_app(), base_url="https://testserver") as client:
        login(client, make_user("admin"))
        r = client.get("/api/v1/_t/cached")
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert r.headers["Cache-Control"] == "private, no-cache"
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        etag = r.headers["ETag"]
        again = client.get("/api/v1/_t/cached", headers={"If-None-Match": etag})
        assert again.status_code == 304 and again.content == b""
        assert again.headers["ETag"] == etag
    with TestClient(_app(), base_url="https://testserver") as other:
        login(other, make_user("economist_filiala", branch_ids=(3,)))
        assert other.get("/api/v1/_t/cached").headers["ETag"] != etag


def test_publish_during_request_sends_no_etag(make_user: Callable[..., SeedUser]) -> None:
    app = create_app()

    @app.get("/api/v1/_t/racy")
    def racy(cache_dep: Cache) -> Response:
        def loader() -> dict[str, int]:
            _publish_new_build()
            return {"v": 2}

        return cache_dep.respond("t.racy", {}, loader)

    with TestClient(app, base_url="https://testserver") as client:
        login(client, make_user("admin"))
        r = client.get("/api/v1/_t/racy")
        assert r.status_code == 200 and r.json() == {"v": 2}
        assert "ETag" not in r.headers
        assert r.headers["Cache-Control"] == "no-store"
        stale = etag_for(current_version_now() - 1, "t.racy", scope_hash(None), filters_hash({}))
        again = client.get("/api/v1/_t/racy", headers={"If-None-Match": stale})
        assert again.status_code == 200
