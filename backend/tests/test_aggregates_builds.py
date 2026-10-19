import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import apply_rls, get_engine, new_session
from app.core.errors import ConflictError
from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.etl.db import etl_transaction
from tests.etl_helpers import (
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

PARAMS = BuildParams(as_of=TEST_AS_OF, date_from=date(2024, 1, 1))


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _scenario(source: str) -> tuple[int, int]:
    """Test filiali: avgust 2026 — kirim 100, chiqim 40; qoldiq 1000 → 1060."""
    tag = new_tag()
    branch = branch_row(tag)
    code = branch["code"]
    bank = {"code": f"ACC-{tag}", "bank_name": "Тест банк", "account_number": f"2021{tag}",
            "currency": "UZS"}
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [branch],
        "dim_bank": [bank],
        "fact_cashflow": [
            cash_row("in", 20260810, code, 100, direction="in", item_code="PKM54-I06"),
            cash_row("out", 20260811, code, 40),
            cash_row("ly1", 20250920, code, 7),
            cash_row("ly2", 20250928, code, 5),
        ],
        "fact_balance": [
            {"doc_type": "statement", "src_id": "b1", "date_id": 20260731, "branch_code": code,
             "bank_code": bank["code"], "balance": 1000},
            {"doc_type": "statement", "src_id": "b2", "date_id": 20260831, "branch_code": code,
             "bank_code": bank["code"], "balance": 1060},
        ],
        "fact_payment_plan": [
            {"doc_type": "payment_plan", "src_id": "p1", "date_id": 20260801, "branch_code": code,
             "item_code": "PKM54-O09", "amount": 50},
        ],
    }
    run_id = open_run(source)
    stage(run_id, source, rows)
    merge_all(run_id, source)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(
            text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"), {"c": code}
        ).scalar_one())
        build_id = builds.create_build(conn, run_id)
        build_all(conn, build_id, PARAMS)
        builds.mark_ready(conn, build_id)
    return branch_id, build_id


def _cash(build_id: int, branch_id: int, month: int, item_code: str | None) -> dict[str, Any]:
    item_sql = "0" if item_code is None else \
        "(SELECT item_id FROM dwh.dim_item WHERE code = :i)"
    with etl_transaction() as conn:
        row = conn.execute(
            text(f"SELECT * FROM mart.agg_cash_month WHERE build_id = :b AND branch_id = :br "
                 f"AND month_id = :m AND item_id = {item_sql}"),
            {"b": build_id, "br": branch_id, "m": month, "i": item_code},
        ).mappings().one()
    return dict(row)


def test_cash_aggregate_items_totals_and_balances(source: str) -> None:
    branch_id, build_id = _scenario(source)
    out = _cash(build_id, branch_id, 202608, "PKM54-O09")
    assert float(out["outflow"]) == 40 and float(out["inflow"]) == 0
    total = _cash(build_id, branch_id, 202608, None)
    assert float(total["inflow"]) == 100 and float(total["outflow"]) == 40
    assert float(total["opening_balance"]) == 1000
    assert float(total["closing_balance"]) == 1060
    assert float(total["diff"]) == 0
    assert total["days_in_period"] == 31
    with etl_transaction() as conn:
        all_branches = conn.execute(
            text("SELECT inflow FROM mart.agg_cash_month WHERE build_id = :b AND branch_id = 0 "
                 "AND month_id = 202608 AND item_id = 0"), {"b": build_id}).scalar_one()
        current_days = conn.execute(
            text("SELECT max(days_in_period) FROM mart.agg_cash_month WHERE build_id = :b "
                 "AND month_id = 202609"), {"b": build_id}).scalar_one()
    assert float(all_branches) >= 100
    assert current_days in (None, 24)


def test_cmp_columns_use_as_of_day(source: str) -> None:
    branch_id, build_id = _scenario(source)
    last_year = _cash(build_id, branch_id, 202509, "PKM54-O09")
    assert float(last_year["outflow"]) == 12
    assert float(last_year["outflow_cmp"]) == 7  # faqat 1..24-kunlar


def test_payments_aggregate_plan_vs_fact(source: str) -> None:
    branch_id, build_id = _scenario(source)
    with etl_transaction() as conn:
        row = conn.execute(
            text("SELECT plan_amount, fact_amount FROM mart.agg_payments_month "
                 "WHERE build_id = :b AND branch_id = :br AND month_id = 202608 AND item_id = "
                 "(SELECT item_id FROM dwh.dim_item WHERE code = 'PKM54-O09')"),
            {"b": build_id, "br": branch_id}).one()
    assert (float(row[0]), float(row[1])) == (50.0, 40.0)


def test_old_months_are_carried_forward_from_active_build(source: str) -> None:
    """Faktlar 5 yil, agregatlar 10 yil: date_from dan oldingi oylar oldingi build'dan olinadi."""
    branch_id, first = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, first, keep=3)
        second = builds.create_build(conn, None)
        build_all(conn, second, BuildParams(as_of=TEST_AS_OF, date_from=date(2026, 1, 1),
                                            keep_from=date(2016, 1, 1)))
    carried = _cash(second, branch_id, 202509, "PKM54-O09")
    assert float(carried["outflow"]) == 12 and float(carried["outflow_cmp"]) == 7
    assert float(_cash(second, branch_id, 202608, None)["outflow"]) == 40


def test_publish_switches_version_and_keeps_three(source: str) -> None:
    created: list[int] = []
    with etl_transaction() as conn:
        for _ in range(4):
            build_id = builds.create_build(conn, None)
            if not created:  # prune mart qatorlarini ham o'chirishini tekshirish uchun
                build_all(conn, build_id, PARAMS)
            builds.mark_ready(conn, build_id)
            builds.publish(conn, build_id, keep=3)
            created.append(build_id)
        assert builds.active_build(conn) == created[-1]
        statuses = dict(conn.execute(
            text("SELECT build_id, status FROM core.builds WHERE build_id = ANY(:ids)"),
            {"ids": created}).all())
        leftovers = conn.execute(
            text("SELECT count(*) FROM mart.agg_cash_month WHERE build_id = :b"),
            {"b": created[0]}).scalar_one()
    assert created[0] not in statuses and leftovers == 0
    assert statuses[created[-1]] == "published"
    assert statuses[created[1]] == statuses[created[2]] == "superseded"


def test_rollback_to_previous_and_explicit(source: str) -> None:
    with etl_transaction() as conn:
        first = builds.create_build(conn, None)
        builds.mark_ready(conn, first)
        builds.publish(conn, first, keep=3)
        second = builds.create_build(conn, None)
        builds.mark_ready(conn, second)
        builds.publish(conn, second, keep=3)
        assert builds.rollback(conn) == first
        assert builds.active_build(conn) == first
        assert builds.rollback(conn, second) == second
        with pytest.raises(ConflictError):
            builds.rollback(conn, 99_999_999)


def test_failed_build_rows_removed(source: str) -> None:
    _, build_id = _scenario(source)
    with etl_transaction() as conn:
        builds.mark_failed(conn, build_id)
        count = conn.execute(text("SELECT count(*) FROM mart.agg_cash_month WHERE build_id = :b"),
                             {"b": build_id}).scalar_one()
        status = conn.execute(text("SELECT status FROM core.builds WHERE build_id = :b"),
                              {"b": build_id}).scalar_one()
        with pytest.raises(ConflictError):
            builds.publish(conn, build_id, keep=3)
    assert (count, status) == (0, "failed")


def test_pub_view_reads_only_active_build(source: str) -> None:
    _, build_id = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, build_id, keep=3)
        expected = conn.execute(
            text("SELECT count(*) FROM mart.agg_cash_month WHERE build_id = :b"),
            {"b": build_id}).scalar_one()
    with new_session() as s:
        apply_rls(s, None)
        seen = s.execute(text("SELECT count(*) FROM pub.agg_cash_month")).scalar_one()
    assert seen == expected


def _plan_nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        yield from _plan_nodes(child)


def test_pub_query_uses_mart_index_not_facts() -> None:
    """UI so'rovi faktlarga tegmaydi va mart PK indeksidan foydalana oladi.

    mart jadvallari kichik (build'ga ~17 filial × 33 oy × ~16 statya ≈ 9 ming qator), shuning
    uchun planner haqiqiy hajmda seq scan tanlashi ham maqbul; bu yerda enable_seqscan=off
    bilan indeks so'rov shakliga mosligini qotiramiz.
    """
    with new_session() as s:
        apply_rls(s, frozenset({3}))
        s.execute(text("SET LOCAL enable_seqscan = off"))
        plan = s.execute(text(
            "EXPLAIN (FORMAT JSON) SELECT month_id, sum(outflow) FROM pub.agg_cash_month "
            "WHERE branch_id = 3 AND item_id = 0 AND month_id BETWEEN 202601 AND 202609 "
            "GROUP BY month_id")).scalar_one()
    root = (plan if isinstance(plan, list) else json.loads(plan))[0]["Plan"]
    nodes = list(_plan_nodes(root))
    relations = {n.get("Relation Name") for n in nodes} - {None}
    assert not any(r.startswith("fact_") for r in relations)
    mart_nodes = [n for n in nodes if n.get("Relation Name") == "agg_cash_month"]
    index_scans = {"Index Scan", "Index Only Scan", "Bitmap Heap Scan"}
    assert mart_nodes and all(n["Node Type"] in index_scans for n in mart_nodes)


# ── Fix round 1 (task-6-findings-r1.md) ──────────────────────────────────────────────────


def test_mark_failed_is_noop_for_published_build(source: str) -> None:
    """I1: `mark_failed` faol/nashr qilingan build'ni "buzib qo'ya olmaydi" — jim no-op."""
    _, build_id = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, build_id, keep=3)
        ok = builds.mark_failed(conn, build_id)
        status = conn.execute(
            text("SELECT status FROM core.builds WHERE build_id = :b"), {"b": build_id}
        ).scalar_one()
        count = conn.execute(
            text("SELECT count(*) FROM mart.agg_cash_month WHERE build_id = :b"),
            {"b": build_id}).scalar_one()
    assert ok is False
    assert status == "published"
    assert count > 0


def test_rollback_to_ready_build_rejected(source: str) -> None:
    """I2: explicit `rollback` hech qachon nashr qilinmagan `ready` build'ga o'ta olmaydi."""
    with etl_transaction() as conn:
        before = builds.active_build(conn)
        build_id = builds.create_build(conn, None)
        builds.mark_ready(conn, build_id)
        with pytest.raises(ConflictError):
            builds.rollback(conn, build_id)
        status = conn.execute(
            text("SELECT status FROM core.builds WHERE build_id = :b"), {"b": build_id}
        ).scalar_one()
        after = builds.active_build(conn)
    assert status == "ready"
    assert after == before


def test_data_version_trigger_rejects_non_publishable_build() -> None:
    """M1: DB darajasidagi himoya — `ugk_app` `core.data_version`ni to'g'ridan-to'g'ri
    (ilova kodini chetlab o'tib) `failed` build'ga ko'rsatib UPDATE qila olmaydi."""
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, None)
        assert builds.mark_failed(conn, build_id) is True
    with new_session() as s, pytest.raises(DBAPIError, match="not publishable"):
        s.execute(
            text("UPDATE core.data_version SET active_build_id = :b WHERE id = 1"),
            {"b": build_id},
        )


def test_prune_removes_stale_unpublished_builds() -> None:
    """M6: `prune` faol bo'lmagan, 7 kundan eski `ready`/`building`/`failed` buildlarni ham
    o'chiradi (nashr qilinmagan yoki abadiy "building"da qolib ketgan)."""
    with etl_transaction() as conn:
        stale_building = builds.create_build(conn, None)
        stale_ready = builds.create_build(conn, None)
        builds.mark_ready(conn, stale_ready)
        stale_failed = builds.create_build(conn, None)
        builds.mark_failed(conn, stale_failed)
        fresh_building = builds.create_build(conn, None)
        conn.execute(
            text("UPDATE core.builds SET created_at = now() - interval '8 days' "
                 "WHERE build_id = ANY(:ids)"),
            {"ids": [stale_building, stale_ready, stale_failed]},
        )
        removed = set(builds.prune(conn, keep=3))
        remaining = set(conn.execute(
            text("SELECT build_id FROM core.builds WHERE build_id = ANY(:ids)"),
            {"ids": [stale_building, stale_ready, stale_failed, fresh_building]},
        ).scalars())
        conn.execute(text("DELETE FROM core.builds WHERE build_id = :b"),
                     {"b": fresh_building})
    assert {stale_building, stale_ready, stale_failed} <= removed
    assert remaining == {fresh_building}


def test_pub_view_and_mart_hide_other_branches_and_branch_zero_for_scoped_session(
    source: str,
) -> None:
    """M7: filialga cheklangan `ugk_app` sessiyasi boshqa filiallarni va "barcha filiallar
    jami" (branch_id=0) qatorini na `pub` view, na to'g'ridan-to'g'ri `mart` SELECT orqali
    ko'ra olmaydi."""
    branch_id, build_id = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, build_id, keep=3)
    with new_session() as s:
        apply_rls(s, frozenset({branch_id}))
        pub_branches = set(s.execute(
            text("SELECT DISTINCT branch_id FROM pub.agg_cash_month")).scalars())
        mart_branches = set(s.execute(
            text("SELECT DISTINCT branch_id FROM mart.agg_cash_month WHERE build_id = :b"),
            {"b": build_id}).scalars())
    assert pub_branches == {branch_id}
    assert mart_branches == {branch_id}


def test_pub_view_scoped_session_reads_only_active_build(source: str) -> None:
    """M7: filialga cheklangan sessiya ham (>= 2 build mavjud bo'lganda) faqat AKTIV
    build qatorlarini ko'radi."""
    branch_id, first = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, first, keep=3)
        second = builds.create_build(conn, None)
        build_all(conn, second, PARAMS)
        builds.mark_ready(conn, second)
        builds.publish(conn, second, keep=3)
        expected = conn.execute(
            text("SELECT count(*) FROM mart.agg_cash_month WHERE build_id = :b "
                 "AND branch_id = :br"), {"b": second, "br": branch_id}).scalar_one()
    with new_session() as s:
        apply_rls(s, frozenset({branch_id}))
        seen = s.execute(
            text("SELECT count(*) FROM pub.agg_cash_month WHERE branch_id = :br"),
            {"br": branch_id}).scalar_one()
    assert expected > 0
    assert seen == expected


def test_branch_zero_totals_equal_sum_of_branches(source: str) -> None:
    """M7: `branch_id = 0` ("barcha filiallar jami") qatori aynan boshqa filiallar
    yig'indisiga teng (aniq, taqriban emas)."""
    _, build_id = _scenario(source)
    with etl_transaction() as conn:
        total = conn.execute(
            text("SELECT inflow, outflow, inflow_cmp, outflow_cmp FROM mart.agg_cash_month "
                 "WHERE build_id = :b AND branch_id = 0 AND month_id = 202608 AND item_id = 0"),
            {"b": build_id}).one()
        summed = conn.execute(
            text("SELECT sum(inflow), sum(outflow), sum(inflow_cmp), sum(outflow_cmp) "
                 "FROM mart.agg_cash_month WHERE build_id = :b AND branch_id <> 0 "
                 "AND month_id = 202608 AND item_id = 0"), {"b": build_id}).one()
    assert tuple(float(v) for v in total) == tuple(float(v) for v in summed)


def test_all_pub_views_are_security_invoker() -> None:
    """M7: strukturaviy tekshiruv — `pub` sxemasidagi HAR BIR view `security_invoker=true`
    bilan yaratilgan (keyingi vazifalar yangi `pub` view qo'shganda ham unutib qo'yilmasin)."""
    with get_engine("migrator").connect() as conn:
        rows = conn.execute(
            text("SELECT c.relname, c.reloptions FROM pg_class c "
                 "JOIN pg_namespace n ON n.oid = c.relnamespace "
                 "WHERE n.nspname = 'pub' AND c.relkind = 'v'")
        ).all()
    assert rows, "pub sxemasida view topilmadi"
    for name, options in rows:
        opts = list(options or ())
        assert "security_invoker=true" in opts, f"pub.{name}: security_invoker=true emas"


# ── Final review (I1): builds status guard ───────────────────────────────────────────────


def test_ugk_app_cannot_supersede_failed_build_then_activate_it() -> None:
    """I1: ikki bosqichli hujum — failed build'ni 'superseded'ga aylantirish — rad etiladi."""
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, None)
        assert builds.mark_failed(conn, build_id) is True
    with new_session() as s, pytest.raises(DBAPIError, match="allowed only for ugk_etl"):
        s.execute(text("UPDATE core.builds SET status = 'superseded' WHERE build_id = :b"),
                  {"b": build_id})


def test_ugk_app_cannot_activate_ready_build() -> None:
    """I1: sifat tekshiruvidan o'tmagan `ready` build'ni ugk_app faol qila olmaydi."""
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, None)
        builds.mark_ready(conn, build_id)
    with new_session() as s, pytest.raises(DBAPIError, match="not publishable"):
        s.execute(text("UPDATE core.data_version SET active_build_id = :b WHERE id = 1"),
                  {"b": build_id})


def test_rollback_as_ugk_app_and_publish_as_etl_still_work(source: str) -> None:
    _, first = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, first, keep=None)
    _, second = _scenario(source)
    with etl_transaction() as conn:
        builds.publish(conn, second, keep=None)
    with new_session() as s:  # API yo'li (ugk_app); commit qilinmaydi
        assert builds.rollback(s.connection(), None) == first
