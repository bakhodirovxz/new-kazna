import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import ConfigError
from app.etl.hr.client import HrApiClient, HrApiError
from app.etl.hr.models import HrFormatError, parse_breakdown, parse_main
from app.etl.hr.source import HrApiSource, MehnatNotConfigured, MehnatSource
from app.etl.types import ConnectorUnavailableError

FIXTURES = Path(__file__).parent / "fixtures" / "hr"
BASE = "https://hr.test"
SECRET = "p@ss-не-логировать"
TOKEN = "tok-secret-123"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _server(log: list[str], *, get_status: list[int] | None = None,
            login_status: int = 200, body: bytes | None = None,
            expires_in: Any = 600) -> Callable[[httpx.Request], httpx.Response]:
    statuses = list(get_status or [])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            log.append("login")
            assert request.headers["content-type"] == "application/x-www-form-urlencoded"
            assert parse_qs(request.content.decode()) == {"username": ["u"],
                                                          "password": [SECRET]}
            if login_status != 200:
                return httpx.Response(login_status, json={"detail": SECRET})
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": expires_in,
                                             "token_type": "bearer"})
        log.append(f"GET {request.url.path} {request.headers.get('authorization')}")
        status = statuses.pop(0) if statuses else 200
        return httpx.Response(status, content=body if body is not None else b'{"ok": true}')

    return handler


def _client(handler: Callable[[httpx.Request], httpx.Response], clock: Clock | None = None,
            **kw: Any) -> HrApiClient:
    return HrApiClient(BASE, "u", SECRET, transport=httpx.MockTransport(handler),
                       clock=clock or Clock(), **kw)


def test_login_once_and_bearer_reused() -> None:
    log: list[str] = []
    client = _client(_server(log))
    assert client.get("/dashboard/main") == {"ok": True}
    client.get("/dashboard/main")
    assert log == ["login", f"GET /dashboard/main Bearer {TOKEN}",
                   f"GET /dashboard/main Bearer {TOKEN}"]
    assert TOKEN not in repr(client) and SECRET not in repr(client)


def test_token_cached_and_refreshed_on_expiry_and_401() -> None:
    log: list[str] = []
    clock = Clock()
    client = _client(_server(log, get_status=[200, 401, 200]), clock)
    client.get("/a")
    clock.now += 600 - 60 + 1  # muddatdan 60 s oldin yangilanadi
    client.get("/b")  # 401 → qayta login → takror
    assert [x for x in log if x == "login"] == ["login", "login", "login"]
    assert log[-1] == f"GET /b Bearer {TOKEN}"


def test_errors_are_classified_and_sanitized() -> None:
    with pytest.raises(HrApiError) as exc:
        _client(_server([], login_status=403)).get("/a")
    assert "учётную запись" in str(exc.value) and SECRET not in str(exc.value)
    with pytest.raises(ConnectorUnavailableError):
        _client(_server([], login_status=503)).get("/a")
    with pytest.raises(ConnectorUnavailableError):
        _client(_server([], get_status=[502])).get("/a")
    with pytest.raises(HrApiError) as twice:
        _client(_server([], get_status=[401, 401])).get("/a")
    assert TOKEN not in str(twice.value)
    with pytest.raises(HrApiError, match="байт"):
        _client(_server([], body=b"x" * 2048), max_bytes=1024).get("/a")
    with pytest.raises(HrApiError, match="JSON"):
        _client(_server([], body=b"<html>")).get("/a")
    log: list[str] = []
    _client(_server(log, expires_in="soon")).get("/a")  # noto'g'ri expires_in → 3600
    with pytest.raises(ConfigError, match="https"):
        HrApiClient("http://hr.test", "u", "p")
    with pytest.raises(ConfigError, match="hr_username"):
        HrApiClient(BASE, "", "p")


def test_parse_main_and_breakdown_shapes() -> None:
    assert parse_main(json.loads((FIXTURES / "main.json").read_text(encoding="utf-8"))) == 100
    assert parse_main({"total_count": 7}) == 7 and parse_main({"x": 1}) is None
    plain = parse_breakdown(json.loads((FIXTURES / "by_category.json").read_text("utf-8")))
    assert [(r.organization, r.category, r.employees) for r in plain] == [
        (None, "Руководители", 12), (None, "Специалисты", 88)]
    assert [r.category for r in parse_breakdown({"Руководители": 3, "Специалисты": 4})] == [
        "Руководители", "Специалисты"]
    rows = parse_breakdown(json.loads((FIXTURES / "by_org.json").read_text(encoding="utf-8")))
    first = rows[0]
    assert (first.organization, first.category, first.employees, first.staff, first.hired,
            first.fired, first.overtime) == ("Чорвоқ ГЭС", "Руководители", 9, 10, 1, 0, 20)
    assert rows[2].staff is None and rows[2].hired is None
    assert "Иванов" not in repr(rows) and "12345678901234" not in repr(rows)
    for bad in ({"data": [{"count": 1}]}, [{"category": "X", "count": -1}], "text",
                [{"category": "X", "count": "много"}]):
        with pytest.raises(HrFormatError):
            parse_breakdown(bad)


def test_api_source_and_mehnat_stub() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 600})
        name = "main.json" if request.url.path == "/dashboard/main" else "by_org.json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes())

    source = HrApiSource(_client(handler), "/dashboard/employees-by-category")
    snap = source.snapshot(date(2026, 9, 24))
    assert snap.as_of == date(2026, 9, 24) and snap.total == 100 and len(snap.rows) == 4
    assert source.healthcheck().ok is True
    down = HrApiSource(_client(_server([], login_status=503)), "/x")
    assert down.healthcheck().ok is False
    with pytest.raises(MehnatNotConfigured, match=r"mehnat\.uz"):
        MehnatSource()


def test_hr_probe_codes_without_secrets_in_result() -> None:
    from app.core import integrations
    from app.core.db import get_engine
    from app.etl import probes
    from tests.helpers import clear_setting, put_setting

    assert probes.hr_probe() == "not_configured"
    put_setting("hr.base_url", "https://hr.test")
    try:
        with get_engine("app").begin() as conn:
            integrations.store_secret(conn, "hr.username", "u", None)
            integrations.store_secret(conn, "hr.password", SECRET, None)
        assert probes.hr_probe(httpx.MockTransport(_server([]))) == "ok"
        assert probes.hr_probe(httpx.MockTransport(_server([], login_status=403))) == "auth_failed"
        assert probes.hr_probe(httpx.MockTransport(_server([], login_status=503))) == "http_error"
        assert "hr" in probes.PROBES
    finally:
        clear_setting("hr.base_url")
        with get_engine("app").begin() as conn:
            integrations.clear_secret(conn, "hr.username")
            integrations.clear_secret(conn, "hr.password")
