import re
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.core.db import get_engine, new_session
from app.dwh import partitions
from app.etl.db import etl_transaction

FACTS = (
    "fact_cashflow", "fact_balance", "fact_payment_plan", "fact_payment_order", "fact_debt",
    "fact_generation", "fact_energy_sales", "fact_procurement", "fact_stock", "fact_stock_move",
    "fact_investment", "fact_loan_schedule", "fact_hr", "fact_target_funds",
    "fact_object_stage",
)
SRC = "test_facts"


@pytest.fixture(autouse=True)
def _cleanup() -> Iterator[None]:
    with etl_transaction() as conn:
        partitions.ensure_partitions(conn, "fact_cashflow", date(2026, 8, 1), date(2026, 9, 30))
    yield
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_cashflow WHERE src_system = :s"), {"s": SRC})


def _item(conn: Connection) -> int:
    return int(conn.execute(
        text("SELECT item_id FROM dwh.dim_item WHERE code = 'PKM54-O09'")).scalar_one())


def _insert_cash(conn: Connection, src_id: str, day: int, item_id: int) -> None:
    conn.execute(
        text("INSERT INTO dwh.fact_cashflow (date_id, branch_id, item_id, direction, amount, "
             "load_id, src_system, doc_type, src_id) "
             "VALUES (:d, 2, :i, 'out', 10.5, 0, :s, 'bank_entry', :sid)"),
        {"d": day, "i": item_id, "s": SRC, "sid": src_id},
    )


def test_all_facts_exist_with_forced_rls() -> None:
    with etl_transaction() as conn:
        rows = conn.execute(
            text("SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                 "JOIN pg_namespace n ON n.oid = c.relnamespace "
                 "WHERE n.nspname = 'dwh' AND c.relname = ANY(:t)"),
            {"t": list(FACTS)},
        ).all()
    assert {r.relname for r in rows} == set(FACTS)
    assert all(r.relrowsecurity and r.relforcerowsecurity for r in rows)


def test_partitioned_unique_key_includes_date() -> None:
    with etl_transaction() as conn:
        item = _item(conn)
        _insert_cash(conn, "doc-1", 20260805, item)
        _insert_cash(conn, "doc-1", 20260910, item)  # boshqa sana — PostgreSQL ruxsat beradi
    with pytest.raises(IntegrityError), etl_transaction() as conn:
        _insert_cash(conn, "doc-1", 20260805, _item(conn))


def test_dimension_fk_is_checked_at_commit() -> None:
    with pytest.raises(IntegrityError), etl_transaction() as conn:
        _insert_cash(conn, "doc-bad", 20260805, 999_999)
        # Deferred FK: shu nuqtagacha xato yo'q, commit'da yiqiladi.
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


def test_ensure_partitions_monthly_and_yearly() -> None:
    with etl_transaction() as conn:
        first = partitions.ensure_partitions(conn, "fact_cashflow", date(2031, 1, 10),
                                             date(2031, 3, 5))
        again = partitions.ensure_partitions(conn, "fact_cashflow", date(2031, 1, 1),
                                             date(2031, 3, 31))
        yearly = partitions.ensure_partitions(conn, "fact_balance", date(2031, 5, 1),
                                              date(2031, 6, 1))
        names = partitions.list_partitions(conn, "fact_cashflow")
    # Test DB konteyneri qayta ishga tushirishlar orasida saqlanadi: birinchi chaqiruv 0 yoki 3.
    assert first in (0, 3)
    assert again == 0
    assert yearly in (0, 1)
    assert {"fact_cashflow_p203101", "fact_cashflow_p203102", "fact_cashflow_p203103"} <= set(names)


def test_ensure_partitions_rejects_unknown_table() -> None:
    with pytest.raises(DBAPIError, match="partitsiyalanmagan"), etl_transaction() as conn:
        conn.execute(text("SELECT dwh.ensure_partitions('fact_hr', date '2026-01-01', "
                          "date '2026-02-01')"))
    with pytest.raises(ValueError), etl_transaction() as conn:
        partitions.ensure_partitions(conn, "core.users", date(2026, 1, 1), date(2026, 1, 2))


def test_drop_old_partitions() -> None:
    with etl_transaction() as conn:
        partitions.ensure_partitions(conn, "fact_balance", date(2016, 1, 1), date(2016, 12, 31))
        dropped = partitions.drop_old(conn, keep_years=5)
        names = partitions.list_partitions(conn, "fact_balance")
    assert dropped >= 1
    assert "fact_balance_p2016" not in names


def test_ensure_ahead_creates_three_months() -> None:
    with etl_transaction() as conn:
        partitions.ensure_ahead(conn, date(2032, 11, 15), months_ahead=3)
        names = set(partitions.list_partitions(conn, "fact_payment_order"))
    assert {"fact_payment_order_p203211", "fact_payment_order_p203302"} <= names


def test_app_role_cannot_read_facts() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("SELECT count(*) FROM dwh.fact_cashflow"))


def test_drop_old_partitions_floor_keeps_two_year_old_partition() -> None:
    """Fix r1 (I1): saqlash pasti hech qachon 5 yildan kam bo'lmaydi
    (`GREATEST(p_keep_years, 5)`, `core.drop_old_audit_partitions`ning 12 oylik pasti bilan
    bir xil naqsh) — `keep_years=1` bilan chaqirilsa ham 2 yillik partitsiya o'chirilmaydi
    (samarali cheklov 5 yil, 2 yil undan yosh)."""
    with etl_transaction() as conn:
        today = conn.execute(text("SELECT (now() AT TIME ZONE 'UTC')::date")).scalar_one()
    year = today.year - 2
    target = f"fact_balance_p{year}"
    with etl_transaction() as conn:
        existed = target in partitions.list_partitions(conn, "fact_balance")
        partitions.ensure_partitions(conn, "fact_balance", date(year, 1, 1), date(year, 12, 31))
        before = set(partitions.list_partitions(conn, "fact_balance"))
    assert target in before
    try:
        with etl_transaction() as conn:
            partitions.drop_old(conn, keep_years=1)
            after = set(partitions.list_partitions(conn, "fact_balance"))
        assert target in after
    finally:
        # DROP TABLE — jadval egasi `ugk_migrator` (SECURITY DEFINER funksiya nomidan
        # yaratilgan), `ugk_etl`ning DROP huquqi yo'q, shuning uchun tozalash migrator
        # ulanishi orqali.
        # Faqat o'zi yaratgan partitsiyani o'chiradi: oldin mavjud bo'lsa (sintetik yuklash
        # `fact_balance_p2024`ni to'ldirgan) o'chirish boshqa testlar ma'lumotini yo'qotadi
        # (task-9 C1 ildizi).
        if not existed:
            with get_engine("migrator").begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS dwh.{target}"))


def test_partitioned_whitelist_matches_sql_function() -> None:
    """Ixtiyoriy paritet tekshiruvi: `app.dwh.partitions.PARTITIONED` (Python) va
    `dwh.ensure_partitions`ning CASE ro'yxati (SQL) mustaqil qo'lda saqlanadi — bu test
    ikkalasi sinxron ekanini isbotlaydi (biri o'zgarib, ikkinchisi unutilsa yiqiladi)."""
    with etl_transaction() as conn:
        src = conn.execute(
            text("SELECT pg_get_functiondef("
                 "'dwh.ensure_partitions(text, date, date)'::regprocedure)")
        ).scalar_one()
    found = dict(re.findall(r"WHEN '(fact_\w+)' THEN '(month|year)'", src))
    assert found == partitions.PARTITIONED


def test_mandatory_indexes_exist() -> None:
    with etl_transaction() as conn:
        names = set(conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'dwh'")).scalars())
    expected = {
        "fact_cashflow_date_id_branch_id_idx",
        "fact_cashflow_branch_id_item_id_idx",
        "fact_cashflow_contract_id_idx",
        "fact_cashflow_date_brin",
        "fact_stock_move_date_brin",
        "fact_debt_contract_id_idx",
        "fact_payment_order_branch_id_date_id_p_idx",
        "fact_debt_branch_id_p_idx",
        "fact_procurement_branch_id_p_idx",
        "fact_cashflow_src_system_doc_type_src_id_idx",
    }
    assert expected <= names
