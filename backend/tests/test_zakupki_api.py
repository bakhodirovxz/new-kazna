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
from tests.s4_helpers import ProcScenario, procurement_scenario, purge_s4, section_branch_role

PAGES = ("svod", "loty", "postavshiki", "ekonomiya")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source, publish=True)
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


def test_svod_numbers_and_etag(sc: ProcScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/zakupki/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["contracted"], k["contracts"], k["savings"], k["savings_share"]) == (
        140.0, 2, 10.0, 0.066667)
    assert (k["plan_execution"], k["in_work"], k["overdue"], k["direct_share"]) == (
        0.197, 1, 1, 0.357143)
    assert k["avg_days"] == 8.5 and body["period"]["code"] == "m08"
    assert body["months"][7] == {"month_id": 202608, "contracted": 140.0}
    assert [m["method"] for m in body["methods"]] == ["eshop", "direct"]
    lot = body["lots"][0]
    assert (lot["lot_no"], lot["kind"], lot["overdue"], lot["date"], lot["days"]) == (
        "L4", "work", True, "2026-07-01", 85)
    again = client.get("/api/v1/zakupki/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_loty_postavshiki_ekonomiya(sc: ProcScenario, app_factory: Callable[[], TestClient],
                                    make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    loty = client.get("/api/v1/zakupki/loty", params=params).json()
    assert [x["lot_no"] for x in loty["lots"]] == ["L4", "L1", "L2", "L6"]
    assert loty["truncated"] is False and loty["lots"][1]["supplier"] == (
        f"ООО «Поставщик-1 {sc.tag}»")
    post = client.get("/api/v1/zakupki/postavshiki", params=params).json()
    assert [(s["name"], s["amount"], s["count"]) for s in post["subjects"]] == [
        ("Запасные части", 90.0, 1), ("Ремонтные услуги", 50.0, 1)]
    assert post["branches"] == [{"branch_id": sc.branch_id, "name": f"Тестовая ГЭС {sc.tag}",
                                 "plan": 1000.0, "ytd": 197.0, "execution": 0.197,
                                 "savings": 10.0}]
    eco = client.get("/api/v1/zakupki/ekonomiya", params=params).json()
    assert eco["methods"][0] == {"method": "eshop", "title": "Электронный магазин", "lots": 1,
                                 "start": 100.0, "contracted": 90.0, "savings": 10.0,
                                 "savings_share": 0.1, "avg_days": 12.0, "norm_days": 15}
    assert [c["lot_no"] for c in eco["cancelled"]] == ["L6"]


def test_permission_and_branch_scope(sc: ProcScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    for role in ("spec_kazna", "economist_filiala"):
        client = _as(app_factory, make_user(role, branch_ids=(sc.branch_id,)))
        for page in PAGES:
            assert client.get(f"/api/v1/zakupki/{page}").status_code == 403, (role, page)
    scoped = _as(app_factory, make_user(section_branch_role("zakupki"),
                                        branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = scoped.get(f"/api/v1/zakupki/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = scoped.get("/api/v1/zakupki/postavshiki", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in own["branches"]} == {sc.branch_id}
    assert own["kpis"]["plan"] == 1000.0 and own["kpis"]["contracted"] == 140.0


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/zakupki/svod", params={"per": "m12"}).status_code == 422


def test_synthetic_procurement(published_synthetic: int, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/zakupki/loty", params={"per": "ytd"}).json()
    kinds = {x["kind"] for x in body["lots"]}
    assert {"work", "done"} <= kinds and body["kpis"]["overdue"] >= 1
    assert 0 < body["kpis"]["plan_execution"] < 1.5


def test_pub_views_rls_direct_sql(sc: ProcScenario) -> None:
    for view in ("agg_procurement_lots", "agg_procurement_plan"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
