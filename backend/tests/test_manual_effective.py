"""0023: dwh.*_effective ustuvorlik view'lari va agregat/sifat o'tishi."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.etl.connectors import make_connector
from app.etl.db import etl_transaction
from app.etl.notify import LogNotifier
from app.etl.runner import Runner, RunResult
from app.etl.types import Mode
from app.main import create_app
from app.manual import approval, store
from app.sections.deps import get_today
from tests.etl_helpers import (
    FULL_WINDOW,
    TEST_AS_OF,
    branch_row,
    cash_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import SeedUser, login
from tests.manual_helpers import (
    balance_item,
    bank_account_item,
    branch_code,
    ctx_of,
    migrator_sql,
    run,
)

EFFECTIVE = [
    ("balance_effective", "fact_balance"),
    ("payment_plan_effective", "fact_payment_plan"),
    ("debt_effective", "fact_debt"),
    ("target_funds_effective", "fact_target_funds"),
    ("loan_schedule_effective", "fact_loan_schedule"),
    ("generation_effective", "fact_generation"),
    ("energy_sales_effective", "fact_energy_sales"),
    ("investment_effective", "fact_investment"),
    ("hr_effective", "fact_hr"),
]


def _count(sql: str, **params: Any) -> int:
    with etl_transaction() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


@pytest.mark.parametrize(("view", "table"), EFFECTIVE)
def test_effective_equals_table_without_manual(
    published_synthetic: int, view: str, table: str
) -> None:
    assert _count(f"SELECT count(*) FROM dwh.{table} WHERE src_system = 'manual'") == 0
    assert _count(f"SELECT count(*) FROM dwh.{table}") > 0 or table in (
        "fact_hr", "fact_investment", "fact_energy_sales", "fact_generation")
    a = _count(f"SELECT count(*) FROM (SELECT * FROM dwh.{table} "
               f"EXCEPT ALL SELECT * FROM dwh.{view}) x")
    b = _count(f"SELECT count(*) FROM (SELECT * FROM dwh.{view} "
               f"EXCEPT ALL SELECT * FROM dwh.{table}) x")
    assert a == b == 0


@pytest.fixture
def bank() -> Iterator[str]:
    """Noyob hisob kodi; test oxirida faqat o'z qatorlari o'chiriladi."""
    code = f"BA-e{uuid.uuid4().hex[:15]}"
    yield code
    with etl_transaction() as conn:  # avval faktlar (boshqa manbalarniki ham), keyin o'lchov
        conn.execute(text("DELETE FROM dwh.fact_balance WHERE bank_id IN "
                          "(SELECT bank_id FROM dwh.dim_bank WHERE code = :c)"), {"c": code})
        conn.execute(text("DELETE FROM dwh.dim_bank WHERE code = :c"), {"c": code})
    purge_source("manual")
    purge_source("filexx")


def _balance(source: str, bank: str, date_id: int, value: str, tag: str = "1") -> None:
    run_id = open_run(source)
    rows = {
        "dim_bank": [{"code": bank, "bank_name": "Тест", "currency": "UZS"}],
        "fact_balance": [{
            "doc_type": "t", "src_id": f"{source}-{tag}-{date_id}", "date_id": date_id,
            "branch_code": branch_code(1), "bank_code": bank, "balance": value}],
    }
    stage(run_id, source, rows)
    merge_all(run_id, source, FULL_WINDOW)


def _drop_facts(bank: str, source: str) -> None:
    with etl_transaction() as conn:
        conn.execute(text(
            "DELETE FROM dwh.fact_balance WHERE src_system = :s AND bank_id IN "
            "(SELECT bank_id FROM dwh.dim_bank WHERE code = :c)"), {"s": source, "c": bank})


def _view_rows(bank: str) -> list[tuple[str, str]]:
    with etl_transaction() as conn:
        return [(r[0], str(r[1])) for r in conn.execute(text(
            "SELECT e.src_system, e.balance FROM dwh.balance_effective e JOIN dwh.dim_bank b "
            "ON b.bank_id = e.bank_id WHERE b.code = :c ORDER BY e.src_system"), {"c": bank})]


def test_system_row_shadows_manual(published_synthetic: int, bank: str) -> None:
    _balance("manual", bank, 20260930, "500.00")
    assert _view_rows(bank) == [("manual", "500.00")]
    _balance("filexx", bank, 20260915, "700.00")  # shu oy, shu hisob -- tizim manbai
    assert _view_rows(bank) == [("filexx", "700.00")]
    _balance("manual", bank, 20261031, "9.00", tag="2")  # boshqa oy -- bo'shliq to'ldiriladi
    assert _view_rows(bank) == [("filexx", "700.00"), ("manual", "9.00")]


def test_manual_shadows_synthetic(published_synthetic: int, bank: str) -> None:
    _balance("synthetic", bank, 20260915, "111.00")
    assert _view_rows(bank) == [("synthetic", "111.00")]
    _balance("manual", bank, 20260930, "222.00")
    assert _view_rows(bank) == [("manual", "222.00")]
    # tizim (fayl) + sintetik: o'zaro yopilmaydi (qo'lda qator bo'lmasa)
    _drop_facts(bank, "manual")
    _balance("filexx", bank, 20260920, "333.00")
    assert {s for s, _ in _view_rows(bank)} == {"filexx", "synthetic"}


def _fact(source: str, target: str, row: dict[str, Any]) -> None:
    run_id = open_run(source)
    stage(run_id, source, {target: [{"branch_code": branch_code(1), **row}]})
    merge_all(run_id, source, FULL_WINDOW)


def _visible(view: str, tag: str) -> set[str]:
    with etl_transaction() as conn:
        return {r[0] for r in conn.execute(text(
            f"SELECT src_system || ':' || doc_type FROM dwh.{view} WHERE src_id LIKE :t"),
            {"t": f"{tag}%"})}


def test_schedule_and_plan_rows_do_not_shadow_each_other(published_synthetic: int) -> None:
    tag = f"T{uuid.uuid4().hex[:8]}"
    base = {"item_code": "PKM54-O09", "amount": 5}
    try:
        _fact("manual", "fact_payment_plan",
              {**base, "doc_type": "manual_plan", "src_id": f"{tag}-m", "date_id": 20260901})
        # kalendar (sanali jadval) qatori oylik rejani yopmaydi
        _fact("filexx", "fact_payment_plan",
              {**base, "doc_type": "payment_schedule", "src_id": f"{tag}-s", "date_id": 20260915})
        assert _visible("payment_plan_effective", tag) == {
            "manual:manual_plan", "filexx:payment_schedule"}
        # 1C reja qatori (boshqa tur) shu oy uchun qo'lda rejani yopadi
        _fact("filexx", "fact_payment_plan",
              {**base, "doc_type": "budget", "src_id": f"{tag}-b", "date_id": 20260901})
        assert _visible("payment_plan_effective", tag) == {
            "filexx:budget", "filexx:payment_schedule"}
    finally:
        purge_source("filexx")
        purge_source("manual")


def test_generation_fact_rows_never_shadowed(published_synthetic: int) -> None:
    tag = f"T{uuid.uuid4().hex[:8]}"
    gen = {"generation": 1, "plan": 2}
    try:
        _fact("manual", "fact_generation",
              {**gen, "doc_type": "generation_plan", "src_id": f"{tag}-m", "date_id": 20260901,
               "generation": 0})
        _fact("filexx", "fact_generation",
              {**gen, "doc_type": "daily", "src_id": f"{tag}-d", "date_id": 20260915})
        assert _visible("generation_effective", tag) == {
            "manual:generation_plan", "filexx:daily"}  # fakt rejani yopmaydi
        _fact("filexx", "fact_generation",
              {**gen, "doc_type": "generation_plan", "src_id": f"{tag}-p", "date_id": 20260901})
        assert _visible("generation_effective", tag) == {
            "filexx:generation_plan", "filexx:daily"}  # tizim rejasi qo'lda rejani yopadi
    finally:
        purge_source("filexx")
        purge_source("manual")



# --- agregatlar va sifat: qo'lda kiritilgan qoldiq «Казначейство» da ------------------------------

class ManualScenario(NamedTuple):
    branch_id: int
    result: RunResult


@pytest.fixture
def manual_sc(make_user: Callable[..., SeedUser]) -> Iterator[ManualScenario]:
    """Izchil tizim hisobi (fayl) + qo'lda kiritilgan hisob: iyul 1000, avgust 1300 (farq 300)."""
    migrator_sql("TRUNCATE core.manual_entry, core.manual_head, core.manual_batch, "
                 "core.etl_requests RESTART IDENTITY")
    source, tag = new_source(), new_tag()
    branch = branch_row(tag)
    code = branch["code"]
    bank = f"ACC-{tag}"
    run_id = open_run(source)
    stage(run_id, source, {
        "dim_branch": [branch],
        "dim_bank": [{"code": bank, "bank_name": "Тест", "currency": "UZS"}],
        "fact_cashflow": [cash_row("c1", 20260805, code, 100, direction="out")],
        "fact_balance": [
            {"doc_type": "statement", "src_id": "b1", "date_id": 20260731, "branch_code": code,
             "bank_code": bank, "balance": 200},
            {"doc_type": "statement", "src_id": "b2", "date_id": 20260831, "branch_code": code,
             "bank_code": bank, "balance": 100},
        ],
    })
    merge_all(run_id, source)
    branch_id = int(migrator_sql(
        "SELECT branch_id FROM dwh.dim_branch WHERE code = :c", c=code)[0][0])
    maker, checker = ctx_of(make_user("spec_kazna")), ctx_of(make_user("nach_otdela"))

    def approve(entity: str, items: list[dict[str, Any]]) -> None:
        b = run(maker, store.create_batch, entity_id=entity, branch_id=branch_id,
                origin="form", items=[store.ItemIn(values=v) for v in items], submit=True)
        run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)

    approve("kazna.bank_account", [bank_account_item(branch_id)])
    acc = migrator_sql("SELECT code FROM core.manual_head")[0][0]
    approve("kazna.balance", [balance_item(acc, "2026-07-31", "1000.00", branch_id),
                              balance_item(acc, "2026-08-31", "1300.00", branch_id)])
    result = Runner(make_connector("manual"), mode=Mode.FULL, notifier=LogNotifier()).run()
    yield ManualScenario(branch_id, result)
    migrator_sql("TRUNCATE core.manual_entry, core.manual_head, core.manual_batch, "
                 "core.etl_requests RESTART IDENTITY")
    purge_source("manual")
    purge_source(source)


def test_manual_balance_reaches_kazna_svod(
    manual_sc: ManualScenario, make_user: Callable[..., SeedUser]
) -> None:
    assert manual_sc.result.status == "success", manual_sc.result.error
    app = create_app()
    app.dependency_overrides[get_today] = lambda: TEST_AS_OF
    with TestClient(app, base_url="https://testserver") as client:
        login(client, make_user("spec_kazna"))
        svod = client.get("/api/v1/kazna/svod",
                          params={"per": "m08", "br": manual_sc.branch_id}).json()
    assert svod["kpis"]["balance"] == 100.0 + 1300.0  # tizim hisobi + qo'lda hisob
    assert svod["kpis"]["banks"] == 2


def test_manual_balance_month_is_unverifiable_not_failed(manual_sc: ManualScenario) -> None:
    result = manual_sc.result
    assert result.status == "success", result.error  # "Разница" 300 publish'ni to'xtatmaydi
    detail = migrator_sql(
        "SELECT detail->'balance_identity' FROM core.etl_step WHERE run_id = :r "
        "AND name = 'quality'", r=result.run_id)[0][0]
    assert detail["ok"] is True
    assert {"branch_id": manual_sc.branch_id, "month_id": 202608,
            "reason": "manual_balance"} in detail["unverifiable"]
    assert not [v for v in detail["violations"] if v["branch_id"] == manual_sc.branch_id]
