"""Pool/threadpool tiqilishi (Plan 4 Task 9 perf): parallel so'rovlar pool'dan ko'p bo'lsa ham
`QueuePool ... timed out` bo'lmasligi kerak.

Mexanizm: so'rov sessiyasi ulanishni `get_ctx`da oladi va endpoint/`get_db` teardown
uchun keyingi threadpool "sakrash"larini kutib turganda ham ushlab turadi. Thread'lar tugab,
hammasi pool'da ulanish kutsa — ulanish egalari esa thread kutsa — `pool_timeout`gacha qotib
qoladi. Test buni kichik pool (1+1) va kichik threadpool (4) bilan tez qayta hosil qiladi.
"""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio.to_thread
import pytest
import structlog
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.auth.context import SESSION_COOKIE
from app.core import db as core_db
from app.core.config import get_settings
from app.main import create_app
from tests.helpers import SeedUser, login

PATHS = ("/api/v1/auth/me", "/api/v1/meta/freshness", "/api/v1/meta/menu")


def _reset_engines() -> None:
    for role in ("app", "etl", "migrator"):
        core_db.get_engine(role).dispose()
    core_db.get_engine.cache_clear()
    core_db._session_factory.cache_clear()
    core_db._slots.clear()


@pytest.fixture
def tiny_pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DB_POOL_SIZE", "1")  # pool 1 + overflow 1 = 2 ulanish
    get_settings.cache_clear()
    _reset_engines()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    _reset_engines()


async def _set_threads(tokens: int) -> int:
    limiter = anyio.to_thread.current_default_thread_limiter()
    previous = int(limiter.total_tokens)
    limiter.total_tokens = tokens
    return previous


def _burst(client: TestClient, token: str, count: int) -> list[int]:
    def one(i: int) -> int:
        path = PATHS[i % len(PATHS)]
        return client.get(path, headers={"Cookie": f"{SESSION_COOKIE}={token}"}).status_code

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(one, range(count)))


@pytest.mark.usefixtures("tiny_pool")
def test_burst_larger_than_pool_and_threadpool_does_not_time_out(
    make_user: Callable[..., SeedUser],
) -> None:
    """Eski kodda: 4 thread ulanish kutadi, 2 ulanish egasi thread kutadi → 10 s timeout, 500."""
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client, make_user("rukovodstvo"))
        token = client.cookies[SESSION_COOKIE]
        previous = client.portal.call(_set_threads, 4)  # type: ignore[union-attr]
        try:
            statuses = _burst(client, token, 24)
        finally:
            client.portal.call(_set_threads, previous)  # type: ignore[union-attr]
    assert statuses == [200] * 24


def test_request_holds_at_most_one_connection(make_user: Callable[..., SeedUser]) -> None:
    """Sahifa endpointlari so'rov boshiga bittadan ortiq ulanishni bir vaqtda olmaydi
    (ichma-ich checkout yo'q) — pool o'lchami `DB_POOL_SIZE`ga nisbatan hisoblanadi."""
    engine = core_db.get_engine("app")
    held: dict[int, str] = {}
    current: dict[str, int] = {}
    peak: dict[str, int] = {}

    def checkout(_dbapi: Any, record: Any, _proxy: Any) -> None:
        rid = structlog.contextvars.get_contextvars().get("request_id")
        if rid is None:
            return
        held[id(record)] = rid
        current[rid] = current.get(rid, 0) + 1
        peak[rid] = max(peak.get(rid, 0), current[rid])

    def checkin(_dbapi: Any, record: Any) -> None:
        rid = held.pop(id(record), None)
        if rid is not None:
            current[rid] -= 1

    event.listen(engine.pool, "checkout", checkout)
    event.listen(engine.pool, "checkin", checkin)
    try:
        with TestClient(create_app(), base_url="https://testserver") as client:
            login(client, make_user("rukovodstvo"))
            token = client.cookies[SESSION_COOKIE]
            peak.clear()
            statuses = _burst(client, token, 12)
    finally:
        event.remove(engine.pool, "checkout", checkout)
        event.remove(engine.pool, "checkin", checkin)
    assert statuses == [200] * 12
    assert peak and max(peak.values()) == 1, peak
