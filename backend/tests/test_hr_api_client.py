import json
import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.config import ConfigError
from app.etl.hr.client import HrApiClient, HrApiError
from app.etl.hr.models import (
    HrFormatError,
    parse_attendance,
    parse_structure,
)
from app.etl.hr.source import HrApiSource, MehnatNotConfigured, MehnatSource
from app.etl.types import ConnectorUnavailableError

FIXTURES = Path(__file__).parent / "fixtures" / "hr"
BASE = "https://hr.test"
KEY = "k3y-SECRET-123"


def _server(log: list[Any], *, status: int = 200, body: bytes | None = None,
            fixture: str | None = None) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.path, dict(request.url.params),
                    request.headers.get("x-api-key"), request.headers.get("authorization")))
        content = body if body is not None else (
            (FIXTURES / fixture).read_bytes() if fixture else b'{"ok": true}')
        return httpx.Response(status, content=content)

    return handler


def _client(handler: Callable[[httpx.Request], httpx.Response], **kw: Any) -> HrApiClient:
    return HrApiClient(BASE, KEY, transport=httpx.MockTransport(handler), **kw)


def test_api_key_header_get_only_no_login_and_not_in_repr() -> None:
    log: list[Any] = []
    client = _client(_server(log))
    assert client.get("/directory/structure", {"include_empty": "false"}) == {"ok": True}
    assert log == [("GET", "/directory/structure", {"include_empty": "false"}, KEY, None)]
    assert KEY not in repr(client) and not hasattr(client, "login")
    assert client.http.trust_env is False and client.http.follow_redirects is False
    assert client.http.timeout.read >= 120


@pytest.mark.parametrize(("status", "body", "exc", "needle"), [
    (403, b'{"code":"forbidden","message":"x"}', HrApiError, "доступ запрещён"),
    (401, b'{}', HrApiError, "доступ запрещён"),
    (503, b'{"code":"directory_disabled","message":"x"}', ConnectorUnavailableError,
     "directory_disabled"),
    (422, '{"code":"invalid_date","message":"bad Каримов"}'.encode(), HrApiError,
     "invalid_date"),
    (502, b'', ConnectorUnavailableError, "HTTP 502"),
    (404, b'{}', ConnectorUnavailableError, "HTTP 404"),
])
def test_errors_are_classified_and_sanitized(status: int, body: bytes, exc: type[Exception],
                                             needle: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(exc) as err:
        _client(_server([], status=status, body=body)).get("/directory/structure")
    assert needle in str(err.value)
    assert KEY not in str(err.value) and "Каримов" not in str(err.value)
    assert KEY not in caplog.text


def test_size_cap_json_and_config_checks() -> None:
    with pytest.raises(HrApiError, match="байт"):
        _client(_server([], body=b"x" * 2048), max_bytes=1024).get("/a")
    with pytest.raises(HrApiError, match="JSON"):
        _client(_server([], body=b"<html>")).get("/a")
    with pytest.raises(ConfigError, match="https"):
        HrApiClient("http://hr.test", KEY)
    with pytest.raises(ConfigError, match=r"hr\.api_key"):
        HrApiClient(BASE, "")


def test_parse_structure_maps_categories_and_ignores_names() -> None:
    snap = parse_structure(json.loads((FIXTURES / "structure.json").read_text("utf-8")))
    rows = {(r.hr_id, r.category): r.employees for r in snap}
    assert rows == {(1, "Руководители"): 4, (1, "Специалисты"): 20, (1, "Без категории"): 6,
                    (6, "Рабочие"): 35, (6, "Служащие"): 5, (10, "Рабочие"): 20,
                    (25, "Руководители"): 10}
    assert "Иванов" not in repr(snap)
    for bad in ({"branches": "x"}, [], {"branches": [{"id": "a", "positions": []}]},
                {"branches": [{"id": 1, "positions": [{"category": "x", "employees_count": -1}]}]}):
        with pytest.raises(HrFormatError):
            parse_structure(bad)


def test_parse_attendance_whitelist_drops_items() -> None:
    rep = parse_attendance(json.loads((FIXTURES / "attendance.json").read_text("utf-8")))
    assert rep.generated_at.isoformat() == "2026-10-28T06:12:41.508000+00:00"
    assert {s.code: (s.label, s.kind) for s in rep.statuses}["new_reason"] == (
        "Yangi sabab", "reason")
    first = rep.branches[0]
    assert (first.hr_id, first.employees, first.by_status["late"]) == (1, 30, (4, 4))
    assert "Каримов" not in repr(rep) and "12345678901234" not in repr(rep)
    assert not hasattr(rep, "items")
    for bad in ({"generated_at": "x", "statuses": [], "branches": []},
                {"generated_at": "2026-10-28T06:00:00Z", "statuses": [], "branches": [
                    {"id": 1, "employees": 1, "by_status": {"present": {"days": -1,
                                                                        "employees": 1}}}]}):
        with pytest.raises(HrFormatError):
            parse_attendance(bad)


def test_api_source_requests_and_mehnat_stub() -> None:
    log: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.url.path, dict(request.url.params)))
        name = "structure.json" if "structure" in request.url.path else "attendance.json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes())

    source = HrApiSource(_client(handler))
    snap = source.snapshot(date(2026, 10, 28))
    assert snap.as_of == date(2026, 10, 28) and snap.total == 100 and len(snap.rows) == 7
    rep = source.attendance(date(2026, 10, 27))
    assert len(rep.branches) == 3
    assert log == [("/directory/structure", {"include_empty": "false"}),
                   ("/directory/attendance", {"size": "1", "include_days": "false",
                                              "date": "2026-10-27"})]
    assert source.healthcheck().ok is True
    assert HrApiSource(_client(_server([], status=503))).healthcheck().ok is False
    with pytest.raises(MehnatNotConfigured, match=r"mehnat\.uz"):
        MehnatSource()


def test_hr_probe_codes_without_secrets_in_result() -> None:
    from app.core import integrations
    from app.core.db import get_engine
    from app.etl import probes
    from tests.helpers import clear_setting, put_setting

    clear_setting("hr.base_url")
    assert probes.hr_probe() == "not_configured"
    put_setting("hr.base_url", "https://hr.test")
    try:
        with get_engine("app").begin() as conn:
            integrations.store_secret(conn, "hr.api_key", KEY, None)
        log: list[Any] = []
        assert probes.hr_probe(httpx.MockTransport(_server(log))) == "ok"
        assert log[0][1:4] == ("/directory/structure", {"include_empty": "false"}, KEY)
        assert probes.hr_probe(httpx.MockTransport(_server([], status=403))) == "auth_failed"
        assert probes.hr_probe(httpx.MockTransport(_server([], status=503))) == "http_error"
        assert probes.hr_probe(httpx.MockTransport(_server([], status=404))) == "http_error"
        assert "hr" in probes.PROBES
    finally:
        clear_setting("hr.base_url")
        with get_engine("app").begin() as conn:
            integrations.clear_secret(conn, "hr.api_key")


def test_api_key_must_be_header_safe_ascii() -> None:
    from app.core.integrations import SECRETS

    sd = SECRETS["hr.api_key"][1]
    assert sd.validate(KEY) == KEY
    for bad in ("ключ", "with space", "tab	x", ""):
        with pytest.raises(ValueError):
            sd.validate(bad)
