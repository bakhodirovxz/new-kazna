import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.dwh.reference import current_setting
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source
from tests.helpers import SeedUser, login, put_setting
from tests.s4_helpers import HrScenario, hr_scenario, purge_s4

PAGES = ("svod", "chislennost", "fot", "dvizhenie")
FORBIDDEN_KEY = re.compile(
    r"^(.*_)?(fio|full_?name|first_?name|last_?name|middle_?name|surname|patronymic|pinfl|"
    r"passport|birth(day|_?date)?|phone|email|address|tabel|employee_?id)(_.*)?$", re.I)


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[HrScenario]:
    source = new_source()
    scenario = hr_scenario(source, publish=True)
    with get_engine("app").connect() as conn:
        kinds = dict(current_setting(conn, "kazna.calendar_kinds"))
    put_setting("kazna.calendar_kinds", {**kinds, "salary": [scenario.salary_code]})
    yield scenario
    put_setting("kazna.calendar_kinds", kinds)
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


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_svod_numbers_and_etag(sc: HrScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/kadry/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["plan"], k["fact"], k["vacancies"], k["vacancy_share"], k["fill"]) == (
        100.0, 90.0, 10.0, 0.1, 0.9)
    assert (k["payroll"], k["payroll_share"], k["avg_salary"], k["turnover"]) == (
        180.0, 0.3, 2.0, 0.033333)
    assert (k["overtime_per_employee"], k["snap_month"]) == (4.666667, 202608)
    assert [c["name"] for c in body["categories"]] == ["Оперативный персонал", "Руководители"]
    assert body["months"][6] == {"month_id": 202607, "payroll": 170.0, "fact": 91.0,
                                 "avg_salary": 1.868132, "hired": 1, "fired": 2,
                                 "overtime": 315.0, "suppressed": False,
                                 "suppressed_reason": None}
    again = client.get("/api/v1/kadry/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_other_pages(sc: HrScenario, app_factory: Callable[[], TestClient],
                     make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "q3", "br": sc.branch_id}
    fot = client.get("/api/v1/kadry/fot", params=params).json()
    assert (fot["kpis"]["payroll"], fot["kpis"]["avg_salary"]) == (500.0, 1.984127)
    assert fot["branches"][0]["payroll"] == 500.0
    dv = client.get("/api/v1/kadry/dvizhenie", params=params).json()
    assert (dv["kpis"]["hired"], dv["kpis"]["fired"], dv["kpis"]["turnover"]) == (6, 7, 0.077778)
    assert dv["branches"][0]["overtime_per_employee"] == 10.5
    ch = client.get("/api/v1/kadry/chislennost", params=params).json()
    assert ch["branches"][0]["vacancies"] == 10.0


def test_permission_and_branch_scope(sc: HrScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    kazna = _as(app_factory, make_user("spec_kazna"))
    for page in PAGES:
        assert kazna.get(f"/api/v1/kadry/{page}").status_code == 403, page
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = econ.get(f"/api/v1/kadry/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = econ.get("/api/v1/kadry/chislennost", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in own["branches"]} == {sc.branch_id}
    assert own["kpis"]["fact"] == 90.0


def test_no_personal_fields_anywhere(sc: HrScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser],
                                     published_synthetic: int) -> None:
    """TZ 9: «Кадры» — faqat agregatlar, ФИО hech qayerda saqlanmaydi va ko'rsatilmaydi."""
    with get_engine("migrator").connect() as conn:
        columns = conn.execute(text(
            "SELECT table_schema || '.' || table_name AS tbl, column_name FROM "
            "information_schema.columns WHERE (table_schema, table_name) IN "
            "(('dwh', 'fact_hr'), ('dwh', 'dim_position'), ('mart', 'agg_hr_month'), "
            "('pub', 'agg_hr_month'))")).all()
    assert {r.tbl for r in columns} == {"dwh.fact_hr", "dwh.dim_position", "mart.agg_hr_month",
                                      "pub.agg_hr_month"}
    assert [r for r in columns if FORBIDDEN_KEY.match(r.column_name)] == []
    client = _as(app_factory, make_user("rukovodstvo"))
    for page in PAGES:
        for params in ({"per": "ytd"}, {"per": "m08", "br": sc.branch_id}):
            body = client.get(f"/api/v1/kadry/{page}", params=params).json()
            bad = {k for k in _keys(body) if FORBIDDEN_KEY.match(k)}
            assert bad == set(), (page, bad)


def test_pub_view_rls_direct_sql(sc: HrScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        seen = set(s.execute(text("SELECT DISTINCT branch_id FROM pub.agg_hr_month")).scalars())
    assert seen <= {sc.branch_id}
    with new_session() as s:
        assert s.execute(text("SELECT count(*) FROM pub.agg_hr_month")).scalar_one() == 0
