from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.dwh.freshness import freshness
from app.main import create_app
from app.meta.menu import build_menu
from app.meta.periods import build_periods
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


def test_meta_requires_session(client: TestClient) -> None:
    for path in ("branches", "periods", "menu", "freshness"):
        assert client.get(f"/api/v1/meta/{path}").status_code == 401


def test_branches_for_global_user_with_etag(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("rukovodstvo"))
    r = client.get("/api/v1/meta/branches")
    assert r.status_code == 200
    items = r.json()
    ids = [b["id"] for b in items]
    assert set(range(1, 17)) <= set(ids)
    assert items[0]["id"] == 1 and items[0]["is_hq"] is True and items[0]["kind"] == "head"
    charvak = next(b for b in items if b["id"] == 2)
    assert charvak["capacity_mw"] == 666.0 and 41 < charvak["lat"] < 42
    assert r.headers["Cache-Control"] == "private, no-cache"
    again = client.get("/api/v1/meta/branches", headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_branch_economist_sees_only_own_branch_even_after_cache_warmup(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    admin = TestClient(client.app, base_url="https://testserver")
    login(admin, make_user("admin"))
    assert len(admin.get("/api/v1/meta/branches").json()) >= 16  # kesh "hammasi" bilan to'ldi
    login(client, make_user("economist_filiala", branch_ids=(3,)))
    assert [b["id"] for b in client.get("/api/v1/meta/branches").json()] == [3]


def test_pub_views_and_mart_rls_direct_sql(published_synthetic: int) -> None:
    queries = {
        "pub.branches": "SELECT DISTINCT branch_id FROM pub.branches",
        "pub.agg_cash_month": "SELECT DISTINCT branch_id FROM pub.agg_cash_month",
        "pub.agg_payments_month": "SELECT DISTINCT branch_id FROM pub.agg_payments_month",
        "mart.agg_cash_month": "SELECT DISTINCT branch_id FROM mart.agg_cash_month",
    }
    with new_session() as s:
        apply_rls(s, frozenset({3}))
        for name, sql in queries.items():
            assert set(s.execute(text(sql)).scalars()) == {3}, name
    with new_session() as s:
        apply_rls(s, None)
        assert 0 in set(s.execute(text(queries["pub.agg_cash_month"])).scalars())
    with new_session() as s:  # doira o'rnatilmagan — hech narsa
        for sql in queries.values():
            assert s.execute(text(sql)).all() == []


def test_periods_builder() -> None:
    periods = build_periods(date(2026, 9, 24))
    assert [p.code for p in periods] == [
        "ytd", "q1", "q2", "q3", "m01", "m02", "m03", "m04", "m05", "m06", "m07", "m08", "m09"]
    labels = {p.code: p.label for p in periods}
    assert labels["ytd"] == "Январь – сентябрь 2026"
    assert labels["q3"] == "III квартал 2026"
    assert labels["m09"] == "Сентябрь 2026"
    q3 = next(p for p in periods if p.code == "q3")
    assert (q3.date_from, q3.date_to) == (date(2026, 7, 1), date(2026, 9, 24))


def test_periods_on_first_of_january() -> None:
    periods = build_periods(date(2027, 1, 1))
    assert [(p.code, p.label) for p in periods] == [
        ("ytd", "Январь 2027"), ("q1", "I квартал 2027"), ("m01", "Январь 2027")]
    assert all(p.date_to == date(2027, 1, 1) for p in periods)


def test_periods_endpoint(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("rukovodstvo"))
    body = client.get("/api/v1/meta/periods").json()
    assert body["default"] == "ytd"
    assert body["items"][0]["code"] == "ytd"


def test_menu_filtered_by_role() -> None:
    econ = {"section:obzor:view", "section:kazna:view", "section:proizvodstvo:view",
            "section:sklad:view", "section:kadry:view"}
    menu = build_menu(frozenset(econ))
    assert [g.title for g in menu.groups] == [None, "Финансы", "Обеспечение", "Производство",
                                              "Персонал"]
    assert [[s.id for s in g.sections] for g in menu.groups] == [
        ["obzor"], ["kazna"], ["sklad"], ["proizvodstvo"], ["kadry"]]
    kazna = menu.groups[1].sections[0]
    assert kazna.title == "Казначейство"
    assert [p.id for p in kazna.pages] == ["svod", "platezhi", "calendar", "dogovory", "celevye"]
    only_obzor = build_menu(frozenset({"section:obzor:view"}))
    assert [g.title for g in only_obzor.groups] == [None]


def test_menu_endpoint_for_admin(client: TestClient, make_user: Callable[..., SeedUser]) -> None:
    login(client, make_user("admin"))
    groups = client.get("/api/v1/meta/menu").json()["groups"]
    assert sum(len(g["sections"]) for g in groups) == 9
    obzor = groups[0]["sections"][0]
    assert [p["title"] for p in obzor["pages"]] == [
        "Сводка", "Требует внимания", "Поступления", "Расходование", "Таблица Excel"]


def test_freshness(client: TestClient, make_user: Callable[..., SeedUser],
                   published_synthetic: int) -> None:
    with get_engine("app").connect() as conn:
        current = freshness(conn, datetime.now(UTC))
        assert current.last_success_at is not None
        later = freshness(conn, current.last_success_at + timedelta(hours=7))
        fresh = freshness(conn, current.last_success_at + timedelta(hours=1))
    assert later.stale is True and fresh.stale is False and later.max_age_hours == 6
    login(client, make_user("economist_filiala", branch_ids=(3,)))
    body = client.get("/api/v1/meta/freshness").json()
    assert body["last_success_at"] is not None and body["max_age_hours"] == 6
    assert body["active_build_id"] == published_synthetic
