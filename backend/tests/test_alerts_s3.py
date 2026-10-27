from collections.abc import Iterator

import pytest
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate, load_rules
from app.alerts.types import REGISTRY
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.etl.db import etl_transaction
from app.sections.deps import SectionQuery
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
from tests.s1_helpers import rebuild
from tests.s3_helpers import (
    ProdScenario,
    StockScenario,
    production_scenario,
    put_rule,
    stock_scenario,
)

PROD = frozenset({"section:proizvodstvo:view"})
SKLAD = frozenset({"section:sklad:view"})


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def prod() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture(scope="module")
def stk() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture(scope="module")
def bare_branch() -> Iterator[int]:
    """1C'ning joriy shakli kabi: qiymat bor, minimum va oxirgi harakat sanasi yo'q."""
    source = new_source()
    tag = new_tag()
    run = open_run(source)
    stage(run, source, {
        "dim_branch": [branch_row(tag)],
        "dim_nomenclature": [{"code": f"ACC-{tag}", "name": "Материалы (10.1)",
                              "category": "Сырьё и материалы", "unit": "—", "enbt_code": None}],
        "fact_stock": [{"doc_type": "onec_stock", "src_id": "x1", "date_id": 20260831,
                        "branch_code": f"T-{tag}", "nom_code": f"ACC-{tag}",
                        "warehouse": "Основной склад", "qty": 0, "value": 50,
                        "min_qty": None, "last_move_date_id": None}],
    })
    merge_all(run, source)
    rebuild(run, publish=True)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": f"T-{tag}"}).scalar_one())
    yield branch_id
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str) -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def test_registry_has_s3_rules() -> None:
    assert {"generation_plan", "energy_payment_level", "stock_below_minimum",
            "illiquid_stock_share"} <= set(REGISTRY)


def test_production_rules_fire(prod: ProdScenario, db: Session) -> None:
    hits, checked = evaluate(db, _q(prod.branch_id, "m08"), PROD)
    assert [h.code for h in hits] == ["generation_plan", "energy_payment_level"]
    plan, pay = hits
    # Stansiya qisqa nomi — tests.etl_helpers.branch_row'dagi short_name.
    assert plan.message.startswith("1 ГЭС не выполняет план выработки: ")
    assert plan.message.endswith(f"{prod.tag} 90%")
    assert (plan.section, plan.page, plan.level, plan.value) == ("proizvodstvo", "stancii",
                                                                  "warning", 1.0)
    assert pay.message == "75,0%: оплачено 900,0 млн из 1,2 млрд" and pay.value == 0.75
    assert pay.page == "realiz"
    assert checked == ["Выполнение плана выработки", "Уровень оплаты за энергию"]
    # m09: bajarilish 83% (reja ulushlangan), to'lov darajasi 90% — faqat reja qoidasi.
    assert [h.code for h in evaluate(db, _q(prod.branch_id, "m09"), PROD)[0]] == [
        "generation_plan"]


def test_production_thresholds_from_db(prod: ProdScenario, db: Session) -> None:
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("generation_plan", threshold={**rules["generation_plan"].threshold,
                                               "value": 0.85})
        put_rule("energy_payment_level", threshold={**rules["energy_payment_level"].threshold,
                                                    "value": 0.7})
        assert evaluate(db, _q(prod.branch_id, "m08"), PROD)[0] == []
    finally:
        put_rule("generation_plan", threshold=rules["generation_plan"].threshold)
        put_rule("energy_payment_level", threshold=rules["energy_payment_level"].threshold)


def test_production_rules_skip_without_data(prod: ProdScenario, db: Session) -> None:
    assert evaluate(db, _q(prod.hq_id, "m08"), PROD)[0] == []
    assert evaluate(db, _q(prod.branch_id, "m01"), PROD)[0] == []  # reja va realizatsiya yo'q
    assert evaluate(db, _q(prod.branch_id, "m08"), SKLAD)[0] == []


def test_stock_rules(stk: StockScenario, db: Session) -> None:
    hits = evaluate(db, _q(stk.branch_id, "m08"), SKLAD)[0]
    assert [h.code for h in hits] == ["illiquid_stock_share"]
    assert hits[0].message == "66,7% стоимости запасов без движения более 180 дней: 80,0 млн"
    assert hits[0].page == "nelikvid" and hits[0].value == pytest.approx(0.666667)
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("stock_below_minimum", threshold={**rules["stock_below_minimum"].threshold,
                                                   "value": 0})
        below = evaluate(db, _q(stk.branch_id, "m08"), SKLAD)[0][0]
        assert below.code == "stock_below_minimum" and below.level == "critical"
        assert below.message == "1 позиция ниже минимального запаса: Подшипник тестовый"
        assert evaluate(db, _q(stk.branch_id, "m09"), SKLAD)[0] == []  # m09: past yo'q, 15%
    finally:
        put_rule("stock_below_minimum", threshold=rules["stock_below_minimum"].threshold)


def test_stock_rules_skip_without_min_or_age(bare_branch: int, db: Session) -> None:
    rules = {r.code: r for r in load_rules(db)}
    try:
        for code in ("stock_below_minimum", "illiquid_stock_share"):
            put_rule(code, threshold={**rules[code].threshold, "value": -1})
        assert evaluate(db, _q(bare_branch, "m08"), SKLAD)[0] == []
    finally:
        for code in ("stock_below_minimum", "illiquid_stock_share"):
            put_rule(code, threshold=rules[code].threshold)
