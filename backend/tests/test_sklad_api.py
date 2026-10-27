from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.helpers import SeedUser, login
from tests.s3_helpers import StockScenario, release_branch, stock_scenario

PAGES = ("svod", "ostatki", "minimum", "nelikvid")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[StockScenario]:
    source = new_source()
    scenario = stock_scenario(source, publish=True)
    yield scenario
    release_branch(scenario.branch_id)
    purge_source(source)


@pytest.fixture
def app_factory() -> Iterator[Callable[[], TestClient]]:
    clients: list[TestClient] = []

    def make() -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _as(app_factory: Callable[[], TestClient], user: SeedUser) -> TestClient:
    return login(app_factory(), user)


def test_svod_numbers_and_etag(sc: StockScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/sklad/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["as_of"], k["value"], k["turnover_days"], k["positions"]) == ("2026-08-31", 120.0,
                                                                             26.6, 3)
    assert (k["below_min"], k["has_minimum"], k["idle_value"], k["idle_share"]) == (
        1, True, 80.0, 0.666667)
    assert (k["inflow"], k["outflow"], k["has_age"], k["has_data"]) == (100.0, 140.0, True, True)
    assert body["months"][7] == {"month_id": 202608, "inflow": 100.0, "outflow": 140.0}
    assert body["categories"] == [{"name": "Запасные части", "amount": 100.0},
                                  {"name": "Масла и ГСМ", "amount": 20.0}]
    assert [p["nom_code"] for p in body["below"]] == [f"N1-{sc.tag}"]
    assert body["below"][0]["coverage"] == 0.4
    again = client.get("/api/v1/sklad/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_ostatki_minimum_nelikvid(sc: StockScenario, app_factory: Callable[[], TestClient],
                                  make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("nach_otdela"))
    params = {"per": "m08", "br": sc.branch_id}
    ost = client.get("/api/v1/sklad/ostatki", params=params).json()
    assert ost["branches"] == [{"branch_id": sc.branch_id, "name": f"Тестовая ГЭС {sc.tag}",
                                "value": 120.0, "positions": 3, "below_min": 1,
                                "idle_value": 80.0}]
    mn = client.get("/api/v1/sklad/minimum", params=params).json()
    assert [(p["warehouse"], p["qty"], p["min_qty"], p["unit"]) for p in mn["below"]] == [
        ("Склад А", 4.0, 10.0, "шт")]
    nel = client.get("/api/v1/sklad/nelikvid", params=params).json()
    assert [a["key"] for a in nel["ages"]] == ["le90", "d91_180", "d181_365", "gt365", "unknown"]
    assert [(p["nom_code"], p["age_days"]) for p in nel["illiquid"]] == [
        (f"N3-{sc.tag}", 456), (f"N2-{sc.tag}", 233)]
    sep = client.get("/api/v1/sklad/nelikvid", params={"per": "m09", "br": sc.branch_id}).json()
    assert sep["ages"][-1] == {"key": "unknown", "value": 60.0}


def test_permission_and_branch_scope(sc: StockScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    kazna = _as(app_factory, make_user("spec_kazna"))
    for page in PAGES:
        assert kazna.get(f"/api/v1/sklad/{page}").status_code == 403, page
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = econ.get(f"/api/v1/sklad/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = econ.get("/api/v1/sklad/ostatki", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in own["branches"]} == {sc.branch_id}
    assert own["kpis"]["value"] == 120.0


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/sklad/svod", params={"per": "q4"}).status_code == 422


def test_synthetic_warehouses(published_synthetic: int, app_factory: Callable[[], TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/sklad/ostatki", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in body["branches"]} >= set(range(1, 17))
    k = body["kpis"]
    assert k["value"] > 0 and k["has_minimum"] and k["has_age"] and k["turnover_days"] > 0
    assert len(body["categories"]) == 7


def test_pub_views_rls_direct_sql(sc: StockScenario) -> None:
    for view in ("agg_stock_month", "agg_stock_positions"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
