from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source
from tests.helpers import SeedUser, login
from tests.s4_helpers import InvScenario, investment_scenario, purge_s4, section_branch_role

PAGES = ("svod", "obekty", "istochniki", "riski")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source, publish=True)
    purge_s4(source)


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


def test_svod_and_obekty(sc: InvScenario, app_factory: Callable[[], TestClient],
                         make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/investicii/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["has_objects"], k["objects"], k["program"], k["plan_to_date"], k["fact_ytd"]) == (
        True, 2, 440.0, 220.0, 180.0)
    assert (k["execution"], k["fact_period"], k["lagging"], k["commissioning"], k["year"]) == (
        0.818182, 130.0, 1, 1, 2026)
    assert len(body["cumulative"]) == 12 and body["cumulative"][7] == {
        "month_id": 202608, "plan": 220.0, "fact": 180.0}
    assert body["cumulative"][9]["fact"] is None
    assert [s["share"] for s in body["sources"]] == [0.375, 0.45]
    first = body["objects"][0]
    assert (first["object_code"], first["status"], first["gap_pp"], first["advance_days"]) == (
        f"OA-{sc.tag}", "lag", 9.0, 91)
    obekty = client.get("/api/v1/investicii/obekty", params=params).json()
    assert [o["object_code"] for o in obekty["objects"]] == [f"OA-{sc.tag}", f"OB-{sc.tag}"]
    again = client.get("/api/v1/investicii/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_istochniki_and_riski(sc: InvScenario, app_factory: Callable[[], TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    ist = client.get("/api/v1/investicii/istochniki", params=params).json()
    assert [s["name"] for s in ist["sources"]] == [f"Бюджет тест {sc.tag}",
                                                   f"МФИ тест {sc.tag}"]
    assert len(ist["cumulative"]) == 12
    riski = client.get("/api/v1/investicii/riski", params=params).json()
    assert [o["object_code"] for o in riski["lagging"]] == [f"OA-{sc.tag}"]
    assert [(o["object_code"], o["gap_pp"]) for o in riski["gaps"]] == [(f"OB-{sc.tag}", 33.0)]
    assert [(o["object_code"], o["advance"], o["advance_days"]) for o in riski["advances"]] == [
        (f"OA-{sc.tag}", 30.0, 91), (f"OB-{sc.tag}", 20.0, 113)]
    stages = riski["stages"][0]
    assert stages["object_id"] == sc.obj_a and stages["late"] == 2
    assert [(s["stage_no"], s["done"], s["late"]) for s in stages["stages"]] == [
        (1, True, False), (2, True, True), (3, False, True), (4, False, False)]
    assert stages["stages"][0]["plan_date"] == "2026-03-15"


def test_branch_without_objects(sc: InvScenario, app_factory: Callable[[], TestClient],
                                make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    for page in PAGES:
        body = client.get(f"/api/v1/investicii/{page}", params={"per": "m08", "br": 1}).json()
        assert body["kpis"]["has_objects"] is False and body["kpis"]["execution"] is None, page


def test_permission_and_branch_scope(sc: InvScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    for role in ("spec_kazna", "economist_filiala"):
        client = _as(app_factory, make_user(role, branch_ids=(sc.branch_id,)))
        for page in PAGES:
            assert client.get(f"/api/v1/investicii/{page}").status_code == 403, (role, page)
    scoped = _as(app_factory, make_user(section_branch_role("investicii"),
                                        branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = scoped.get(f"/api/v1/investicii/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = scoped.get("/api/v1/investicii/obekty", params={"per": "m08"}).json()
    assert {o["branch_id"] for o in own["objects"]} == {sc.branch_id}


def test_synthetic_program(published_synthetic: int, app_factory: Callable[[], TestClient],
                           make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/investicii/obekty", params={"per": "m08"}).json()
    synthetic = [o for o in body["objects"] if o["object_code"].startswith("OBJ-")]
    assert len(synthetic) == 14
    assert all(o["execution"] is not None and 0 < o["financial"] < 1 for o in synthetic)


def test_pub_views_rls_direct_sql(sc: InvScenario) -> None:
    for view in ("agg_investment_month", "agg_object_stages"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
