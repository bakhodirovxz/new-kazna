from collections.abc import Iterator

import pytest
import redis
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate, load_rules
from app.alerts.types import REGISTRY
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.sections.deps import SectionQuery
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s2_helpers import LoanScenario, loan_scenario, put_rule

KRED = frozenset({"section:kredity:view"})


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str = "m08") -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def test_registry_has_loan_rules() -> None:
    assert {"loan_payments_30d", "fx_loans_share"} <= set(REGISTRY)


def test_loan_rules_fire_on_scenario(sc: LoanScenario, db: Session) -> None:
    hits, checked = evaluate(db, _q(sc.branch_id), KRED)
    assert [h.code for h in hits] == ["loan_payments_30d", "fx_loans_share"]
    payments, share = hits
    assert payments.message == f"1 платёж на 1,5 млрд, первый 15.09.2026 — Тест кредитор А {sc.tag}"
    assert (payments.section, payments.page, payments.level, payments.value) == (
        "kredity", "grafik", "warning", 1.0)
    assert share.message == "95,7% портфеля в валюте: 9,0 млрд из 9,4 млрд"
    assert share.page == "svod" and share.value == pytest.approx(9000 / 9400)
    assert checked == ["Платежи по кредитам", "Доля валютных кредитов"]


def test_thresholds_come_from_db(sc: LoanScenario, db: Session) -> None:
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("loan_payments_30d", threshold={**rules["loan_payments_30d"].threshold,
                                                 "value": 10})
        put_rule("fx_loans_share", threshold={**rules["fx_loans_share"].threshold,
                                              "value": 0.99})
        assert evaluate(db, _q(sc.branch_id), KRED)[0] == []
        put_rule("loan_payments_30d", threshold={**rules["loan_payments_30d"].threshold,
                                                 "value": 45})
        hits = evaluate(db, _q(sc.branch_id), KRED)[0]
        assert hits[0].message.startswith("2 платежа на 1,6 млрд, первый 15.09.2026")
    finally:
        put_rule("loan_payments_30d", threshold=rules["loan_payments_30d"].threshold)
        put_rule("fx_loans_share", threshold=rules["fx_loans_share"].threshold)


def test_no_loans_or_missing_rates_do_not_fire(sc: LoanScenario, db: Session) -> None:
    assert evaluate(db, _q(sc.empty_branch_id), KRED)[0] == []
    # m01: XTL kursi yo'q — ulush faqat ma'lum (UZS) qism bo'yicha 0, to'lovlar 30 kundan uzoq.
    assert evaluate(db, _q(sc.branch_id, "m01"), KRED)[0] == []
    assert evaluate(db, _q(sc.branch_id), frozenset({"section:obzor:view"}))[0] == []
