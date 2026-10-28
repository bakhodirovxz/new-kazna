import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF
from tests.helpers import SeedUser, login
from tests.s5_helpers import fin_value, put_fin, scoped_role

URL = "/api/v1/finmodel/model"


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


def _pub(scenario: str) -> dict[int, dict[str, Any]]:
    with new_session() as s:
        apply_rls(s, None)
        rows = s.execute(text("SELECT * FROM pub.agg_finmodel_year WHERE scenario = :s"),
                         {"s": scenario}).mappings().all()
    return {int(r["year"]): dict(r) for r in rows}


def _opt(value: Any) -> Any:
    return None if value is None else pytest.approx(float(value))


@pytest.mark.usefixtures("published_synthetic")
def test_model_payload_matches_pub_rows(app_factory: Callable[[], TestClient],
                                        make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("spec_kazna"))
    r = client.get(URL, params={"scen": "water"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["has_model"], body["scenario"], body["company_wide"]) == (True, "water", False)
    pub = _pub("water")
    assert [y["year"] for y in body["years"]] == sorted(pub) == list(range(2026, 2033))
    for y in body["years"]:
        row = pub[y["year"]]
        assert y["revenue"] == pytest.approx(float(row["revenue"]))
        assert y["balance"] == pytest.approx(float(row["balance"]))
        assert y["dscr"] == _opt(row["dscr"])
        assert y["covenant_breach"] is row["covenant_breach"]
    assert [s["scenario"] for s in body["scenarios"]] == ["base", "water", "tariff", "fx"]
    assert (body["summary"]["scenario"], body["summary"]["title"]) == ("water", "Маловодье")
    assert body["summary"]["verdict"] in ("funded", "needs_financing")
    assert {x["scenario"] for x in body["sensitivity"]} == {"water", "tariff", "fx"}
    assert body["base"]["covenant"] == 1.2 and body["base"]["stale_assumptions"] is False
    base = {y["year"]: y for y in client.get(URL).json()["years"]}
    for y in body["years"]:
        factor = 0.85 if 2027 <= y["year"] <= 2029 else 1.0
        assert y["generation"] == pytest.approx(base[y["year"]]["generation"] * factor,
                                                abs=0.002)
    again = client.get(URL, params={"scen": "water"},
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_scenario_validation_and_permissions(app_factory: Callable[[], TestClient],
                                             make_user: Callable[..., SeedUser]) -> None:
    admin = _as(app_factory, make_user("rukovodstvo"))
    assert admin.get(URL, params={"scen": "bad"}).status_code == 422
    economist = _as(app_factory, make_user("economist_filiala", branch_ids=(3,)))
    assert economist.get(URL).status_code == 403
    profile = _as(app_factory, make_user("profil_sluzhba"))
    assert profile.get(URL).status_code == 403
    anonymous = app_factory()
    assert anonymous.get(URL).status_code == 401


@pytest.mark.usefixtures("published_synthetic")
def test_branch_scoped_role_gets_no_model(app_factory: Callable[[], TestClient],
                                          make_user: Callable[..., SeedUser]) -> None:
    code = scoped_role(f"s5fm_{uuid.uuid4().hex[:6]}", ("section:finmodel:view",))
    client = _as(app_factory, make_user(code, branch_ids=(3,)))
    r = client.get(URL, params={"br": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["has_model"], body["years"], body["base"]) == (False, [], None)
    assert client.get(URL, params={"br": 5}).status_code == 403  # doiradan tashqari filial


@pytest.mark.usefixtures("published_synthetic")
def test_company_wide_flag(app_factory: Callable[[], TestClient],
                           make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    whole = client.get(URL).json()
    branch = client.get(URL, params={"br": 3}).json()
    assert (whole["company_wide"], branch["company_wide"]) == (False, True)
    assert branch["years"] == whole["years"]


@pytest.mark.usefixtures("published_synthetic")
def test_stale_assumptions_flag(app_factory: Callable[[], TestClient],
                                make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get(URL).json()["base"]["stale_assumptions"] is False
    original = fin_value("base", 2031, "opex_index")
    put_fin("base", 2031, "opex_index", original + Decimal("0.01"))
    try:
        assert client.get(URL).json()["base"]["stale_assumptions"] is True
    finally:
        put_fin("base", 2031, "opex_index", original)


@pytest.mark.usefixtures("published_synthetic")
def test_kredity_dscr_from_model(app_factory: Callable[[], TestClient],
                                 make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    base = _pub("base")
    svod = client.get("/api/v1/kredity/svod", params={"per": "ytd"}).json()
    assert base[2026]["dscr"] is not None
    assert svod["kpis"]["dscr"] == pytest.approx(float(base[2026]["dscr"]))
    reestr = client.get("/api/v1/kredity/reestr", params={"per": "ytd"}).json()
    assert reestr["kpis"]["dscr"] == svod["kpis"]["dscr"]
    branch = client.get("/api/v1/kredity/svod", params={"per": "ytd", "br": 2}).json()
    assert branch["kpis"]["dscr"] is None  # DSCR — kompaniya ko'rsatkichi
