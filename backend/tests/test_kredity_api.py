from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.helpers import SeedUser, login
from tests.s2_helpers import LoanScenario, kredity_branch_role, loan_scenario

PAGES = ("svod", "reestr", "grafik")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    scenario = loan_scenario(source, publish=True)
    yield scenario
    with get_engine("migrator").begin() as conn:  # chegaralangan rol foydalanuvchisi filialga bog'langan
        conn.execute(text("DELETE FROM core.position_branches WHERE branch_id IN (:a, :b)"),
                     {"a": scenario.branch_id, "b": scenario.empty_branch_id})
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


def test_svod_numbers_and_etag(sc: LoanScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/kredity/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert body["has_loans"] is True and body["period"]["code"] == "m08"
    assert (k["as_of"], k["loans"], k["portfolio"]) == ("2026-08-31", 2, 9400.0)
    assert (k["service"], k["paid"]) == (3208.0, 1630.0)
    assert k["rate"] == pytest.approx(522 / 9400) and k["fx_share"] == pytest.approx(9000 / 9400)
    assert k["paid_share"] == pytest.approx(1630 / 3208)
    assert k["next_payment"]["day"] == "2026-09-15" and k["next_payment"]["total"] == 1460.0
    assert (k["peak_year"], k["peak_amount"]) == (2028, 7350.0)
    assert k["dscr"] is None and k["missing_fx"] == []
    assert [y["year"] for y in body["schedule"]] == list(range(2026, 2036))
    assert body["schedule"][0] == {"year": 2026, "principal": 2200.0, "interest": 1008.0}
    assert body["currencies"] == [{"name": "XTL", "amount": 9000.0},
                                  {"name": "UZS", "amount": 400.0}]
    assert len(body["upcoming"]) == 5
    again = client.get("/api/v1/kredity/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_reestr_and_grafik(sc: LoanScenario, app_factory: Callable[[], TestClient],
                           make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("spec_kazna"))
    params = {"per": "m08", "br": sc.branch_id}
    reestr = client.get("/api/v1/kredity/reestr", params=params).json()
    rows = reestr["loans"]
    assert [x["loan_id"] for x in rows] == [sc.loan_a, sc.loan_b]
    a = rows[0]
    assert (a["loan_code"], a["currency"], a["outstanding"], a["outstanding_cur"]) == (
        f"LA-{sc.tag}", "XTL", 9000.0, 9.0)
    assert a["repaid_share"] == pytest.approx(0.1) and a["in_grace"] is False
    assert (a["grace_until"], a["maturity"], a["branch_id"]) == ("2026-01-01", "2028-12-31",
                                                                  sc.branch_id)
    assert reestr["creditors"][0] == {"name": f"Тест кредитор А {sc.tag}", "amount": 9000.0}
    grafik = client.get("/api/v1/kredity/grafik", params=params).json()
    assert [p["day"] for p in grafik["upcoming"]] == [
        "2026-09-15", "2026-10-10", "2027-03-15", "2027-10-10", "2028-03-15"]
    assert grafik["upcoming"][0]["creditor"] == f"Тест кредитор А {sc.tag}"
    assert len(grafik["schedule"]) == 10


def test_branch_without_loans(sc: LoanScenario, app_factory: Callable[[], TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/kredity/svod",
                      params={"per": "m08", "br": sc.empty_branch_id}).json()
    assert body["has_loans"] is False and body["kpis"]["portfolio"] is None
    assert body["kpis"]["next_payment"] is None and body["upcoming"] == []


def test_permission_and_branch_scope(sc: LoanScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(3,)))
    for page in PAGES:
        assert econ.get(f"/api/v1/kredity/{page}").status_code == 403, page
    limited = _as(app_factory, make_user(kredity_branch_role(), branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = limited.get(f"/api/v1/kredity/{page}", params={"br": sc.empty_branch_id})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = limited.get("/api/v1/kredity/reestr", params={"per": "m08"}).json()
    assert {x["branch_id"] for x in own["loans"]} == {sc.branch_id}
    assert own["kpis"]["portfolio"] == 9400.0


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/kredity/svod", params={"per": "m12"}).status_code == 422


def test_synthetic_portfolio(published_synthetic: int, app_factory: Callable[[], TestClient],
                             make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/kredity/reestr", params={"per": "m08"}).json()
    codes = {x["loan_code"] for x in body["loans"]}
    assert {f"LOAN-{n:02d}" for n in range(1, 9)} <= codes
    assert {"USD", "EUR", "CNY", "UZS"} <= {c["name"] for c in body["currencies"]}
    assert body["kpis"]["portfolio"] > 0 and body["kpis"]["missing_fx"] == []


def test_pub_views_rls_direct_sql(sc: LoanScenario) -> None:
    for view in ("agg_loan_month", "agg_loan_schedule"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
