from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.helpers import SeedUser, login
from tests.s1_helpers import Scenario, treasury_scenario

PAGES = ("svod", "platezhi", "calendar", "dogovory", "celevye")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture
def client_for() -> Iterator[Callable[[SeedUser], TestClient]]:
    opened: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return login(client, user)

    yield make
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def sc() -> Iterator[Scenario]:
    source = new_source()
    yield treasury_scenario(source, publish=True)
    purge_source(source)


def test_kazna_requires_section_permission(client_for: Callable[[SeedUser], TestClient],
                                           make_user: Callable[..., SeedUser]) -> None:
    auditor = client_for(make_user("vnutr_kontrol"))
    for page in PAGES:
        assert auditor.get(f"/api/v1/kazna/{page}").status_code == 403, page


def test_kazna_pages_on_scenario(client_for: Callable[[SeedUser], TestClient],
                                 make_user: Callable[..., SeedUser], sc: Scenario) -> None:
    client = client_for(make_user("spec_kazna"))
    params = {"per": "m08", "br": sc.branch_id}
    svod = client.get("/api/v1/kazna/svod", params=params).json()
    k = svod["kpis"]
    assert (k["balance"], k["plan"], k["fact"], k["execution"]) == (1060.0, 50.0, 40.0, 0.8)
    assert (k["orders_count"], k["orders_amount"]) == (3, 17.0)
    assert (k["requests_count"], k["requests_amount"]) == (2, 11.0)
    assert (k["receivable"], k["payable"], k["overdue_payable"], k["banks"]) == \
        (50.0, 100.0, 0.0, 2)
    assert k["balance_date"] == "2026-08-31"
    assert [o["status"] for o in svod["orders"]][4] == "исполнено"
    assert svod["plan_fact"][0]["deviation"] == 10.0
    assert svod["calendar"]["total"] == 130.0 and svod["calendar"]["start"] == "2026-09-25"
    platezhi = client.get("/api/v1/kazna/platezhi", params={"per": "m09", "br": sc.branch_id})
    assert platezhi.json()["plan_fact"][0]["execution"] == 0.4
    item = client.get(f"/api/v1/kazna/platezhi/items/{sc.item_out_id}", params=params).json()
    assert [(r["fact"], r["plan"]) for r in item["rows"]] == [(40.0, 50.0)]
    cal = client.get("/api/v1/kazna/calendar", params=params).json()
    assert len(cal["calendar"]["days"]) == 14 and cal["calendar"]["balance"] == 1078.0
    assert cal["calendar"]["coverage"] == pytest.approx(1078 / 130)
    assert [b["balance"] for b in cal["banks"]] == [700.0, 360.0]
    assert [(r["count"], r["amount"]) for r in cal["requests"]] == [(2, 11.0)]
    dog = client.get("/api/v1/kazna/dogovory", params={"per": "m09", "br": sc.branch_id}).json()
    assert [(c["overdue_days"], c["amount"]) for c in dog["contracts"]] == [(95, 120.0)]
    assert dog["by_branch"][0]["overdue_payable"] == 60.0
    cel = client.get("/api/v1/kazna/celevye", params={"per": "q3", "br": sc.branch_id}).json()
    assert [(s["allocated"], s["used"], s["share"]) for s in cel["sources"]] == [(20.0, 10.0, 0.5)]


def test_branch_user_scope_on_kazna(client_for: Callable[[SeedUser], TestClient],
                                    make_user: Callable[..., SeedUser],
                                    published_synthetic: int) -> None:
    econ = client_for(make_user("economist_filiala", branch_ids=(3,)))
    for page in PAGES:
        denied = econ.get(f"/api/v1/kazna/{page}", params={"br": 5})
        assert denied.status_code == 403, page
        assert econ.get(f"/api/v1/kazna/{page}").status_code == 200, page
    dog = econ.get("/api/v1/kazna/dogovory").json()
    assert {c["branch_id"] for c in dog["contracts"]} <= {3}
    cal = econ.get("/api/v1/kazna/calendar").json()
    assert {r["branch_id"] for r in cal["requests"]} <= {3}
    etag = econ.get("/api/v1/kazna/svod").headers["ETag"]
    assert econ.get("/api/v1/kazna/svod", headers={"If-None-Match": etag}).status_code == 304
