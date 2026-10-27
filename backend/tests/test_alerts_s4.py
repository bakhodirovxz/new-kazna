from collections.abc import Iterator

import pytest
import redis
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate, load_rules
from app.alerts.types import REGISTRY
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.sections.deps import SectionQuery
from tests.etl_helpers import TEST_AS_OF, new_source
from tests.s2_helpers import put_rule
from tests.s4_helpers import (
    HrScenario,
    InvScenario,
    ProcScenario,
    hr_scenario,
    investment_scenario,
    procurement_scenario,
    purge_s4,
)

ZAK = frozenset({"section:zakupki:view"})
INV = frozenset({"section:investicii:view"})
HR = frozenset({"section:kadry:view"})
S4_RULES = {"procurement_overdue_lots", "direct_contracts_share", "procurement_plan",
            "investment_schedule", "fin_phys_gap", "advances_90d", "vacancies_share",
            "turnover", "overtime"}


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def proc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source, publish=True)
    purge_s4(source)


@pytest.fixture(scope="module")
def inv() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source, publish=True)
    purge_s4(source)


@pytest.fixture(scope="module")
def staff() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source, publish=True)
    purge_s4(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str) -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def test_registry_has_s4_rules() -> None:
    assert set(REGISTRY) >= S4_RULES


def test_procurement_rules(proc: ProcScenario, db: Session) -> None:
    hits = {h.code: h for h in evaluate(db, _q(proc.branch_id, "m08"), ZAK)[0]}
    assert set(hits) == {"direct_contracts_share", "procurement_plan"}
    assert hits["direct_contracts_share"].message == (
        "35,7% суммы договоров заключено без конкурса: 50,0 млн")
    assert hits["procurement_plan"].message == (
        "Исполнено 19,7%: 197,0 млн из 1,0 млрд с начала года")
    assert hits["procurement_plan"].page == "svod"
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("procurement_overdue_lots",
                 threshold={**rules["procurement_overdue_lots"].threshold, "value": 0})
        found = evaluate(db, _q(proc.branch_id, "m08"), ZAK)[0]
        assert found[0].code == "procurement_overdue_lots" and found[0].level == "critical"
        assert found[0].message == (
            "1 лот закупки просрочен: начальная цена 80,0 млн, дольше норматива на 10+ дней")
        assert (found[0].page, found[0].value) == ("loty", 1.0)
    finally:
        put_rule("procurement_overdue_lots",
                 threshold=rules["procurement_overdue_lots"].threshold)


def test_investment_rules(inv: InvScenario, db: Session) -> None:
    hits = {h.code: h for h in evaluate(db, _q(inv.branch_id, "m08"), INV)[0]}
    assert set(hits) == {"investment_schedule", "fin_phys_gap", "advances_90d"}
    assert hits["investment_schedule"].message == (
        "Исполнение графика 81,8%: освоено 180,0 млн из 220,0 млн")
    assert hits["fin_phys_gap"].message == (
        f"1 объект: финансирование опережает физическое выполнение, наибольший разрыв — "
        f"Объект Б {inv.tag} 33 п.п.")
    assert hits["advances_90d"].message == "2 незакрытых аванса старше 90 дней на сумму 50,0 млн"
    assert (hits["advances_90d"].value, hits["fin_phys_gap"].page) == (2.0, "riski")


def test_hr_rules(staff: HrScenario, db: Session) -> None:
    assert evaluate(db, _q(staff.branch_id, "m08"), HR)[0] == []  # 10% — «> 10%» emas
    rules = {r.code: r for r in load_rules(db)}
    changes = {"vacancies_share": 0.05, "turnover": 0.01, "overtime": 4}
    try:
        for code, value in changes.items():
            put_rule(code, threshold={**rules[code].threshold, "value": value})
        hits = {h.code: h for h in evaluate(db, _q(staff.branch_id, "m08"), HR)[0]}
        assert hits["vacancies_share"].message == "10,0% штата не занято: 10 вакансий из 100"
        assert hits["turnover"].message == "Текучесть 3,3%: уволено 3 из 90 работников за период"
        assert hits["overtime"].message == (
            "4,7 ч сверхурочных на работника: всего 420 ч за период")
        assert hits["overtime"].page == "dvizhenie" and hits["vacancies_share"].page == (
            "chislennost")
    finally:
        for code in changes:
            put_rule(code, threshold=rules[code].threshold)


def test_rules_skip_without_data(proc: ProcScenario, inv: InvScenario, staff: HrScenario,
                                 db: Session) -> None:
    every = ZAK | INV | HR
    assert evaluate(db, _q(999_999, "m08"), every)[0] == []
    assert evaluate(db, _q(staff.branch_id, "m06"), HR)[0] == []
    assert evaluate(db, _q(inv.branch_id, "m08"), ZAK | HR)[0] == []  # obyekt filiali
    assert evaluate(db, _q(proc.branch_id, "m08"), HR)[0] == []
