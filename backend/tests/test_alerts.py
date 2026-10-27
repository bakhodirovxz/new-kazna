import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate, load_rules
from app.alerts.types import REGISTRY, RuleConfig
from app.core.config import get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.main import create_app
from app.sections.deps import SectionQuery, get_today
from app.sections.fmt import plural
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
from tests.s1_helpers import Scenario, rebuild, treasury_scenario

ALL = frozenset({"section:obzor:view", "section:kazna:view"})


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[Scenario]:
    source = new_source()
    yield treasury_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str = "m09") -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def _rule(code: str, op: str, value: float) -> RuleConfig:
    return RuleConfig(code, code, "kazna", "svod", "critical", {"metric": "x", "op": op,
                                                                  "value": value})


def _put_rule(code: str, **changes: Any) -> None:
    with get_engine("app").begin() as conn:
        row = conn.execute(text("SELECT * FROM core.alert_rules WHERE code = :c AND is_current"),
                           {"c": code}).mappings().one()
        data = {**dict(row), **changes}
        conn.execute(text("UPDATE core.alert_rules SET is_current = false "
                          "WHERE code = :c AND is_current"), {"c": code})
        conn.execute(text(
            "INSERT INTO core.alert_rules (code, version, title, section, page, threshold, level, "
            "enabled) VALUES (:code, :v, :title, :section, :page, CAST(:th AS jsonb), :level, "
            ":en)"),
            {"code": code, "v": row["version"] + 1, "title": data["title"],
             "section": data["section"], "page": data["page"],
             "th": json.dumps(data["threshold"]), "level": data["level"],
             "en": data["enabled"]})


def test_plural() -> None:
    assert [plural(n, "договор", "договора", "договоров") for n in (1, 3, 5, 11, 21, 22)] == [
        "договор", "договора", "договоров", "договоров", "договор", "договора"]


def test_registry_has_treasury_rules() -> None:
    assert {"cash_below_monthly_outflow", "payments_14d_exceed_balance",
            "payment_plan_execution", "contracts_overdue_90d",
            "overdue_payables_share"} <= set(REGISTRY)


def test_default_rules_on_scenario_critical_first(sc: Scenario, db: Session) -> None:
    hits, checked = evaluate(db, _q(sc.branch_id), ALL)
    assert [h.code for h in hits] == ["contracts_overdue_90d", "payment_plan_execution",
                                      "overdue_payables_share"]
    assert hits[0].level == "critical" and hits[0].page == "dogovory"
    assert hits[0].message == (f"1 договор просрочен более 90 дней на сумму 60,0 млн, "
                               f"крупнейший: ООО «Тест Поставщик {sc.tag}»")
    assert hits[1].message == "исполнение 40,0%, отклонение 18,0 млн"
    assert hits[2].message == "60,0 млн из 120,0 млн кредиторской задолженности (50,0%)"
    assert len(checked) == 5


def test_balance_rules_fire_with_custom_thresholds(sc: Scenario, db: Session) -> None:
    cash_hit = REGISTRY["cash_below_monthly_outflow"](
        db, _q(sc.branch_id), _rule("cash_below_monthly_outflow", "<", 100))
    assert cash_hit is not None and cash_hit.value == pytest.approx(1078 / 15)
    assert cash_hit.message == "1,1 млрд при среднем расходовании 15,0 млн в месяц"
    cal_hit = REGISTRY["payments_14d_exceed_balance"](
        db, _q(sc.branch_id), _rule("payments_14d_exceed_balance", ">", 0.1))
    assert cal_hit is not None and cal_hit.value == pytest.approx(130 / 1078)
    assert cal_hit.message == "к оплате 130,0 млн за 14 дней, на счетах 1,1 млрд"


def test_balance_rules_skip_without_balances(db: Session) -> None:
    source = new_source()
    try:
        branch = branch_row(new_tag())
        run = open_run(source)
        stage(run, source, {"dim_branch": [branch], "fact_cashflow": [
            {"doc_type": "bank_entry", "src_id": "n1", "date_id": 20260905,
             "branch_code": branch["code"], "item_code": "PKM54-O09", "direction": "out",
             "amount": 5}], "fact_payment_plan": [
            {"doc_type": "payment_schedule", "src_id": "n2", "date_id": 20260928,
             "branch_code": branch["code"], "item_code": "PKM54-O09", "amount": 9}]})
        merge_all(run, source)
        rebuild(run, publish=True)
        branch_id = db.execute(text("SELECT branch_id FROM pub.branches WHERE code = :c"),
                               {"c": branch["code"]}).scalar_one()
        for code in ("cash_below_monthly_outflow", "payments_14d_exceed_balance"):
            assert REGISTRY[code](db, _q(branch_id), _rule(code, "<", 1e9)) is None
            assert REGISTRY[code](db, _q(branch_id), _rule(code, ">", -1e9)) is None
    finally:
        purge_source(source)


def test_threshold_change_and_disable(sc: Scenario, db: Session) -> None:
    rule = next(r for r in load_rules(db) if r.code == "contracts_overdue_90d")
    try:
        _put_rule("contracts_overdue_90d", threshold={**rule.threshold, "value": 95})
        assert "contracts_overdue_90d" not in [h.code for h in evaluate(db, _q(sc.branch_id),
                                                                        ALL)[0]]
        _put_rule("contracts_overdue_90d", threshold=rule.threshold, enabled=False)
        codes = [r.code for r in load_rules(db)]
        assert "contracts_overdue_90d" not in codes
    finally:
        _put_rule("contracts_overdue_90d", threshold=rule.threshold, enabled=True)


def test_rules_of_forbidden_sections_are_hidden(sc: Scenario, db: Session) -> None:
    hits, checked = evaluate(db, _q(sc.branch_id), frozenset({"section:obzor:view"}))
    assert hits == [] and checked == []


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


def test_vnimanie_endpoints(sc: Scenario, client_for: Callable[[SeedUser], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    boss = client_for(make_user("rukovodstvo"))
    params = {"per": "m09", "br": sc.branch_id}
    body = boss.get("/api/v1/obzor/vnimanie", params=params).json()
    assert [i["code"] for i in body["items"]] == ["contracts_overdue_90d",
                                                  "payment_plan_execution",
                                                  "overdue_payables_share"]
    assert body["items"][0]["section"] == "kazna" and body["period"]["code"] == "m09"
    assert boss.get("/api/v1/obzor/vnimanie/count", params=params).json() == {
        "count": 3, "critical": 1}
    # Bir xil doira (hammasi), boshqa ruxsatlar: kesh boshqa foydalanuvchining natijasini bermaydi.
    profile = client_for(make_user("profil_sluzhba"))
    assert profile.get("/api/v1/obzor/vnimanie", params=params).json()["items"] == []
    assert profile.get("/api/v1/obzor/vnimanie/count", params=params).json()["count"] == 0
    econ = client_for(make_user("economist_filiala", branch_ids=(3,)))
    assert econ.get("/api/v1/obzor/vnimanie", params=params).status_code == 403
