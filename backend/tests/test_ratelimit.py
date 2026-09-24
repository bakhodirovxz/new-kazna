import uuid

import pytest
import redis

from app.core import ratelimit
from app.core.errors import RateLimitedError
from app.core.ratelimit import Limit


def test_limit_exceeded_raises_with_retry_after() -> None:
    ident = uuid.uuid4().hex
    limit = Limit(events=3, window=60)
    assert [ratelimit.check("t", ident, limit) for _ in range(3)] == [2, 1, 0]
    with pytest.raises(RateLimitedError) as exc:
        ratelimit.check("t", ident, limit)
    assert 1 <= exc.value.params["retry_after"] <= 60
    assert exc.value.headers["Retry-After"] == str(exc.value.params["retry_after"])


def test_identities_are_independent_and_reset_works() -> None:
    a, b = uuid.uuid4().hex, uuid.uuid4().hex
    limit = Limit(events=1, window=60)
    ratelimit.check("t", a, limit)
    ratelimit.check("t", b, limit)
    ratelimit.reset("t", a)
    assert ratelimit.check("t", a, limit) == 0


def test_redis_down_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "_last_failure", 0.0)  # test oxirida qayta tiklanadi
    dead = redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.2, socket_connect_timeout=0.2)
    monkeypatch.setattr(ratelimit, "_client_override", dead)
    limit = Limit(events=1, window=60)
    assert ratelimit.check("t", "x", limit) == 1
    assert ratelimit.check("t", "x", limit) == 1
    assert ratelimit.ping() is False


def test_ping_ok() -> None:
    assert ratelimit.ping() is True
