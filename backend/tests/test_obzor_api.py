from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import (
    TEST_AS_OF,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import SeedUser, login
from tests.s1_helpers import rebuild

NEW_VIEWS = ("agg_cash_bank_month", "agg_payment_orders_month", "agg_target_funds_month",
             "agg_debt_contracts", "agg_debt_month", "agg_calendar_day")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


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


def test_svod_shape_and_etag(app_factory: Callable[[], TestClient],
                             make_user: Callable[..., SeedUser], published_synthetic: int) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    r = client.get("/api/v1/obzor/svod", params={"per": "m08"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"]["code"] == "m08" and body["period"]["open_last"] is False
    assert body["kpis"]["inflow"] > 0 and body["kpis"]["has_data"] is True
    assert body["kpis"]["closing"] is not None
    assert [m["month_id"] for m in body["months"]] == [202600 + m for m in range(1, 10)]
    assert [a["activity"] for a in body["activity"]] == ["centralized", "operating", "investing"]
    assert {s["branch_id"] for s in body["stations"]} >= set(range(1, 17))
    assert all(s["production"] is None for s in body["stations"])
    assert body["items_out"] and body["items_in"]
    again = client.get("/api/v1/obzor/svod", params={"per": "m08"},
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_branch_user_cannot_request_other_branch(app_factory: Callable[[], TestClient],
                                                 make_user: Callable[..., SeedUser],
                                                 published_synthetic: int) -> None:
    client = _as(app_factory, make_user("economist_filiala", branch_ids=(3,)))
    for path in ("svod", "postup", "rasxod", "excel"):
        r = client.get(f"/api/v1/obzor/{path}", params={"br": 4})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", path


def test_branch_user_sees_only_own_data(app_factory: Callable[[], TestClient],
                                        make_user: Callable[..., SeedUser],
                                        published_synthetic: int) -> None:
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(3,)))
    boss = _as(app_factory, make_user("rukovodstvo"))
    mine = econ.get("/api/v1/obzor/svod").json()
    assert {b["branch_id"] for b in mine["branches"]} == {3}
    assert [s["branch_id"] for s in mine["stations"]] == [3]
    assert mine["kpis"] == boss.get("/api/v1/obzor/svod", params={"br": 3}).json()["kpis"]
    detail = econ.get("/api/v1/obzor/excel").json()["detail"]
    assert detail and {d["branch_id"] for d in detail} == {3}


def test_limited_scope_without_br_sees_own_totals(app_factory: Callable[[], TestClient],
                                                  make_user: Callable[..., SeedUser],
                                                  published_synthetic: int) -> None:
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(3, 4)))
    boss = _as(app_factory, make_user("rukovodstvo"))
    both = econ.get("/api/v1/obzor/svod", params={"per": "q2"}).json()["kpis"]
    k3 = boss.get("/api/v1/obzor/svod", params={"per": "q2", "br": 3}).json()["kpis"]
    k4 = boss.get("/api/v1/obzor/svod", params={"per": "q2", "br": 4}).json()["kpis"]
    everyone = boss.get("/api/v1/obzor/svod", params={"per": "q2"}).json()["kpis"]
    assert both["inflow"] == pytest.approx(k3["inflow"] + k4["inflow"], abs=0.01)
    assert both["inflow"] < everyone["inflow"]


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    for per in ("m12", "bad", "q5"):
        assert client.get("/api/v1/obzor/svod", params={"per": per}).status_code == 422, per


def test_flow_excel_and_item_pages(app_factory: Callable[[], TestClient],
                                   make_user: Callable[..., SeedUser],
                                   published_synthetic: int) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    postup = client.get("/api/v1/obzor/postup", params={"per": "q3"}).json()
    assert postup["direction"] == "in" and 1 <= len(postup["series"]) <= 4
    assert all(len(s["values"]) == len(postup["months"]) == 9 for s in postup["series"])
    assert postup["banks"] and postup["branches"] and postup["activity"] == []
    rasxod = client.get("/api/v1/obzor/rasxod", params={"per": "q3"}).json()
    assert [s["key"] for s in rasxod["series"]] == ["centralized", "operating", "investing"]
    assert len(rasxod["activity"]) == 3
    excel = client.get("/api/v1/obzor/excel", params={"per": "m08"}).json()
    assert excel["total"]["inflow"] == pytest.approx(excel["kpis"]["inflow"], abs=0.01)
    assert excel["total"]["branch_id"] == 0
    assert sum(b["inflow"] for b in excel["branches"]) == pytest.approx(excel["total"]["inflow"],
                                                                         abs=0.05)
    item_id = client.get("/api/v1/obzor/svod", params={"per": "m08"}).json()["items_out"][0][
        "item_id"]
    item = client.get(f"/api/v1/obzor/items/{item_id}", params={"per": "m08"}).json()
    assert item["item"]["direction"] == "out" and item["rows"]
    assert any(row["plan"] for row in item["rows"])
    assert client.get("/api/v1/obzor/items/999999").status_code == 404


def test_svod_without_balances_returns_nulls(app_factory: Callable[[], TestClient],
                                             make_user: Callable[..., SeedUser]) -> None:
    source = new_source()
    try:
        branch = branch_row(new_tag())
        run = open_run(source)
        stage(run, source, {"dim_branch": [branch], "fact_cashflow": [
            {"doc_type": "bank_entry", "src_id": "x1", "date_id": 20260805,
             "branch_code": branch["code"], "item_code": "PKM54-O09", "direction": "out",
             "amount": 5}]})
        merge_all(run, source)
        rebuild(run, publish=True)
        with new_session() as s:
            apply_rls(s, None)
            branch_id = s.execute(text("SELECT branch_id FROM pub.branches WHERE code = :c"),
                                  {"c": branch["code"]}).scalar_one()
        client = _as(app_factory, make_user("rukovodstvo"))
        kpis = client.get("/api/v1/obzor/svod", params={"per": "m08", "br": branch_id}).json()[
            "kpis"]
        assert (kpis["outflow"], kpis["opening"], kpis["closing"], kpis["diff"]) == \
            (5.0, None, None, None)
    finally:
        purge_source(source)


def test_new_pub_views_rls_direct_sql(published_synthetic: int) -> None:
    for view in NEW_VIEWS:
        with new_session() as s:
            apply_rls(s, frozenset({3}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {3}, view
    with new_session() as s:
        apply_rls(s, frozenset({3}))
        assert s.execute(text("SELECT count(*) FROM pub.agg_calendar_day")).scalar_one() == 56
    with new_session() as s:
        for view in NEW_VIEWS:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view


def test_numeric_per_alias(app_factory: Callable[[], TestClient],
                           make_user: Callable[..., SeedUser], published_synthetic: int) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    alias = client.get("/api/v1/obzor/svod", params={"per": "08"})
    full = client.get("/api/v1/obzor/svod", params={"per": "m08"})
    assert alias.status_code == 200 and alias.json()["period"]["code"] == "m08"
    assert alias.headers["ETag"] == full.headers["ETag"]
    assert client.get("/api/v1/obzor/svod", params={"per": "13"}).status_code == 422
