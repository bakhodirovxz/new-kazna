import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.etl.db import etl_transaction
from app.etl.hr import attendance
from app.etl.hr.models import parse_attendance
from app.main import create_app
from app.sections.deps import get_today
from app.sections.proizvodstvo import get_now
from tests.helpers import SeedUser, login, put_setting
from tests.test_kadry_api import FORBIDDEN_KEY

FIXTURE = Path(__file__).parent / "fixtures" / "hr" / "attendance.json"
DAY = date(2026, 10, 28)
GEN = datetime(2026, 10, 28, 6, 12, 41, 508000, tzinfo=UTC)
ORGS = [{"org": "x", "branch_code": "UGE-02", "hr_id": 1},
        {"org": "y", "branch_code": "UGE-03", "hr_id": 6}]
URL = "/api/v1/kadry/yavka"


@pytest.fixture
def seeded() -> Iterator[None]:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_attendance WHERE att_date >= '2026-10-01'"))
        attendance.store(conn, parse_attendance(json.loads(FIXTURE.read_text("utf-8"))),
                         [attendance.HrOrg.model_validate(o) for o in ORGS])
    put_setting("hr.attendance_stale_minutes", 30)
    yield
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_attendance WHERE att_date >= '2026-10-01'"))


@pytest.fixture
def make_client() -> Iterator[Callable[[datetime, date], TestClient]]:
    clients: list[TestClient] = []

    def make(now: datetime, today: date = DAY) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: today
        app.dependency_overrides[get_now] = lambda: now
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_empty_when_no_source(make_client: Callable[..., TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    body = login(make_client(GEN), make_user("rukovodstvo")).get(URL).json()
    assert body["has_source"] is False and body["branches"] == [] and body["date"] is None


def test_totals_groups_and_branches(seeded: None, make_client: Callable[..., TestClient],
                                    make_user: Callable[..., SeedUser]) -> None:
    resp = login(make_client(GEN + timedelta(minutes=5)), make_user("rukovodstvo")).get(URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["has_source"], body["stale"], body["date"]) == (True, False, "2026-10-28")
    assert body["generated_at"].startswith("2026-10-28T06:12:41")
    # UGE-02: 20+4 / 2 abs / trip 2 / rest 2 (30); UGE-03: 30+6 / 3 abs / other 1 (40)
    assert body["totals"] == {"employees": 70, "on_work": 60, "late": 10, "absent": 5,
                              "trip": 2, "sick": 0, "leave": 0, "other_reason": 1, "rest": 2}
    assert {(s["code"], s["label"], s["kind"], s["employees"]) for s in body["statuses"]} >= {
        ("new_reason", "Yangi sabab", "reason", 1), ("business_trip", "Xizmat safari", "reason", 2)}
    rows = {b["name"]: b for b in body["branches"]}
    assert len(rows) == 2
    first = next(b for b in body["branches"] if b["employees"] == 40)
    assert (first["on_work"], first["late"], first["absent"], first["attendance_rate"]) == (
        36, 6, 3, 0.9)
    assert [b["employees"] for b in body["branches"]] == [40, 30]  # численность убывает
    assert not any(FORBIDDEN_KEY.match(k) for k in _keys(body))
    assert "Каримов" not in resp.text


def _keys(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def test_stale_and_scope(seeded: None, make_client: Callable[..., TestClient],
                         make_user: Callable[..., SeedUser]) -> None:
    old = login(make_client(GEN + timedelta(minutes=45)), make_user("rukovodstvo")).get(URL).json()
    assert old["stale"] is True
    econ = login(make_client(GEN), make_user("economist_filiala", branch_ids=(3,)))
    own = econ.get(URL).json()
    assert [b["employees"] for b in own["branches"]] == [40] and own["totals"]["employees"] == 40
    assert econ.get(URL, params={"br": 2}).status_code == 403
    kazna = login(make_client(GEN), make_user("spec_kazna"))
    assert kazna.get(URL).status_code == 403


def test_yesterday_shown_when_nothing_today(seeded: None, make_client: Callable[..., TestClient],
                                            make_user: Callable[..., SeedUser]) -> None:
    client = login(make_client(GEN + timedelta(days=1), DAY + timedelta(days=1)),
                   make_user("rukovodstvo"))
    body = client.get(URL).json()
    assert body["date"] == "2026-10-28" and body["stale"] is True


def test_small_group_is_suppressed(seeded: None, make_client: Callable[..., TestClient],
                                   make_user: Callable[..., SeedUser]) -> None:
    put_setting("kadry.min_group", 41)
    try:
        econ = login(make_client(GEN), make_user("economist_filiala", branch_ids=(3,)))
        body = econ.get(URL).json()
    finally:
        put_setting("kadry.min_group", 5)
    assert body["suppressed"] is True and body["statuses"] == []
    assert body["totals"]["employees"] == 40 and body["totals"]["sick"] is None
    row = body["branches"][0]
    assert row["suppressed"] is True and row["on_work"] is None and row["attendance_rate"] is None
    ok = login(make_client(GEN), make_user("rukovodstvo")).get(URL).json()
    assert ok["suppressed"] is False and ok["totals"]["on_work"] == 60
