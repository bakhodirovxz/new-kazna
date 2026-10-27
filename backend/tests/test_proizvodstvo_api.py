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
from tests.s3_helpers import ProdScenario, production_scenario, release_branch

PAGES = ("svod", "stancii", "realiz")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[ProdScenario]:
    source = new_source()
    scenario = production_scenario(source, publish=True)
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


def test_svod_numbers_map_and_etag(sc: ProdScenario, app_factory: Callable[[], TestClient],
                                   make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/proizvodstvo/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert body["has_stations"] is True and body["period"]["code"] == "m08"
    assert (k["generation"], k["generation_prev"], k["plan"], k["execution"]) == (1.8, 1.5, 2.0,
                                                                                 0.9)
    assert (k["capacity_mw"], k["stations"], k["kium"]) == (100.0, 1, 0.024194)
    assert (k["supply"], k["own_share"], k["payment_level"]) == (1.76, 0.022222, 0.75)
    assert [m["month_id"] for m in body["months"]] == list(range(202601, 202610))
    assert body["months"][7] == {"month_id": 202608, "generation": 1.8, "plan": 2.0,
                                 "generation_prev": 1.5}
    assert [s["branch_id"] for s in body["stations"]] == [sc.branch_id]
    by_map = {s["branch_id"]: s for s in body["map"]}
    assert by_map[sc.branch_id]["production"]["execution"] == 0.9
    assert by_map[sc.hq_id]["production"] is None and by_map[sc.hq_id]["kind"] == "head"
    again = client.get("/api/v1/proizvodstvo/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_stancii_and_realiz(sc: ProdScenario, app_factory: Callable[[], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m09", "br": sc.branch_id}
    st = client.get("/api/v1/proizvodstvo/stancii", params=params).json()
    row = st["stations"][0]
    assert (row["generation"], row["plan"], row["execution"], row["kium"]) == (1.0, 1.2, 0.833333,
                                                                              0.017361)
    assert (row["capacity_mw"], row["supply"], row["name"]) == (100.0, 0.98,
                                                                f"Тестовая ГЭС {sc.tag}")
    realiz = client.get("/api/v1/proizvodstvo/realiz", params={"per": "m08",
                                                               "br": sc.branch_id}).json()
    assert realiz["months"][7] == {"month_id": 202608, "accrued": 1200.0, "paid": 900.0}
    assert realiz["stations"][0]["payment_level"] == 0.75


def test_hq_has_no_stations(sc: ProdScenario, app_factory: Callable[[], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    for page in PAGES:
        body = client.get(f"/api/v1/proizvodstvo/{page}",
                          params={"per": "m08", "br": sc.hq_id}).json()
        assert body["has_stations"] is False and body["stations"] == [], page
        assert body["kpis"]["has_data"] is False and body["kpis"]["execution"] is None, page


def test_permission_and_branch_scope(sc: ProdScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    kazna = _as(app_factory, make_user("spec_kazna"))
    for page in PAGES:
        assert kazna.get(f"/api/v1/proizvodstvo/{page}").status_code == 403, page
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = econ.get(f"/api/v1/proizvodstvo/{page}", params={"br": sc.hq_id})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = econ.get("/api/v1/proizvodstvo/stancii", params={"per": "m08"}).json()
    assert {s["branch_id"] for s in own["stations"]} == {sc.branch_id}
    assert own["kpis"]["generation"] == 1.8
    svod = econ.get("/api/v1/proizvodstvo/svod", params={"per": "m08"}).json()
    assert {s["branch_id"] for s in svod["map"]} == {sc.branch_id}


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/proizvodstvo/svod", params={"per": "m12"}).status_code == 422


def test_synthetic_stations(published_synthetic: int, app_factory: Callable[[], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/proizvodstvo/stancii", params={"per": "m08"}).json()
    synthetic = [s for s in body["stations"] if s["branch_id"] <= 16]
    assert len(synthetic) == 15
    assert all(s["execution"] is not None and 0 < s["kium"] < 1 for s in synthetic)
    assert body["kpis"]["payment_level"] is not None
    obzor = client.get("/api/v1/obzor/svod", params={"per": "m08"}).json()
    prod = {s["branch_id"]: s["production"] for s in obzor["stations"]}
    assert prod[1] is None and prod[2] is not None and prod[2]["generation"] > 0


def test_pub_views_rls_direct_sql(sc: ProdScenario) -> None:
    for view in ("agg_generation_month", "agg_energy_sales_month"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
