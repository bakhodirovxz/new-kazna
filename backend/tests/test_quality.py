from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.dwh import builds
from app.dwh.targets import OTHER_OUT_ITEM
from app.etl import merge as merge_module
from app.etl.db import etl_transaction
from app.etl.quality import CHECK_CODES, CheckResult, failed, run_checks
from app.etl.types import ControlTotals, Window
from tests.etl_helpers import (
    FULL_WINDOW,
    branch_row,
    cash_row,
    load_and_build,
    new_source,
    new_tag,
    purge_source,
)


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _check(source: str, rows: dict[str, list[dict[str, Any]]],
           totals: ControlTotals | None = None) -> dict[str, CheckResult]:
    run_id, build_id = load_and_build(source, rows)
    with etl_transaction() as conn:
        results = run_checks(conn, run_id=run_id, build_id=build_id, source=source,
                             window=FULL_WINDOW, totals=totals)
    assert [r.code for r in results] == list(CHECK_CODES)
    return {r.code: r for r in results}


def _clean(tag: str, **branch: Any) -> dict[str, list[dict[str, Any]]]:
    b = branch_row(tag, **branch)
    return {"dim_branch": [b],
            "fact_cashflow": [cash_row("c1", 20260805, b["code"], 100),
                              cash_row("c2", 20260906, b["code"], 50, direction="in",
                                       item_code="PKM54-I06")]}


def _branch_id(code: str) -> int:
    with etl_transaction() as conn:
        return int(conn.execute(
            text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"), {"c": code}
        ).scalar_one())


def test_clean_data_passes_all_checks(source: str) -> None:
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("100"), 202609: Decimal("50")}))
    assert failed(list(results.values())) == []


def test_control_totals_mismatch_fails(source: str) -> None:
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("101"), 202609: Decimal("50")}))
    assert not results["control_totals"].ok
    assert results["control_totals"].detail["mismatches"][0]["month"] == 202608


def test_control_totals_within_tolerance_pass(source: str) -> None:
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("100.05"), 202609: Decimal("50")}))
    assert results["control_totals"].ok


def test_missing_month_in_source_totals_fails(source: str) -> None:
    results = _check(source, _clean(new_tag()), ControlTotals({202608: Decimal("100")}))
    assert not results["control_totals"].ok


def test_control_totals_zero_expected_nonzero_actual_fails(source: str) -> None:
    # M6: kutilgan 0 bo'lsa ham, haqiqiy 0 dan farqli bo'lsa — mos kelmaslik (tolerantlik
    # 0 × 0,1% = 0, shuning uchun har qanday farq buziladi deb hisoblanadi).
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("0"), 202609: Decimal("50")}))
    assert not results["control_totals"].ok
    assert results["control_totals"].detail["mismatches"][0]["month"] == 202608


def test_control_totals_none_totals_skips(source: str) -> None:
    # M6: `totals=None` → tekshiruv o'zi "ok" va sabab aniq ko'rsatilgan bo'lishi kerak.
    results = _check(source, _clean(new_tag()), None)
    assert results["control_totals"].ok
    assert results["control_totals"].detail == {"skipped": True}


def test_control_totals_ignores_months_outside_window(source: str) -> None:
    # M5: manba nazorat summasida oynadan tashqari oy bo'lsa, u mos kelmaslikka
    # hisoblanmaydi — alohida `ignored_months`da ro'yxatga olinadi.
    window = Window(date(2026, 8, 1), date(2026, 8, 31))
    run_id, build_id = load_and_build(source, _clean(new_tag()), window=window)
    with etl_transaction() as conn:
        results = {
            r.code: r for r in run_checks(
                conn, run_id=run_id, build_id=build_id, source=source, window=window,
                totals=ControlTotals({202608: Decimal("100"), 202609: Decimal("999")}))
        }
    assert results["control_totals"].ok
    assert results["control_totals"].detail["ignored_months"] == [202609]


def test_error_counts_scoped_to_own_run(source: str) -> None:
    # M6: boshqa run'ning etl_error qatorlari bu run'ning hisobotiga aralashmaydi.
    other_source = new_source()
    try:
        dirty_rows = _clean(new_tag())
        dirty_rows["fact_cashflow"].append(cash_row("bad", 20260805, "NO-BRANCH", 5))
        load_and_build(other_source, dirty_rows)
        results = _check(source, _clean(new_tag()))
        assert results["mandatory_dims"].ok
        assert results["mandatory_dims"].detail["logged_errors"] == 0
    finally:
        purge_source(other_source)


def test_balance_identity_violation_fails(source: str) -> None:
    tag = new_tag()
    rows = _clean(tag)
    code = rows["dim_branch"][0]["code"]
    rows["dim_bank"] = [{"code": f"ACC-{tag}", "bank_name": "Тест", "currency": "UZS"}]
    rows["fact_balance"] = [
        {"doc_type": "statement", "src_id": "o", "date_id": 20260731, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 1000},
        # To'g'risi 900 (1000 − 100); 800 — farq 100, oborot 100 ning 1% idan katta.
        {"doc_type": "statement", "src_id": "c", "date_id": 20260831, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 800},
        {"doc_type": "statement", "src_id": "s", "date_id": 20260924, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 850},
    ]
    results = _check(source, rows)
    bid = _branch_id(code)
    # M1: faqat SHU testning filialiga tegishli buzilishlarni tekshiramiz — parallel/qoldiq
    # testlar ma'lumoti bilan to'liq ro'yxat tengligini talab qilmaymiz.
    mine = [v for v in results["balance_identity"].detail["violations"] if v["branch_id"] == bid]
    assert not results["balance_identity"].ok
    assert len(mine) == 1
    assert mine[0]["month_id"] == 202608


def test_balance_identity_small_difference_passes(source: str) -> None:
    tag = new_tag()
    rows = _clean(tag)
    code = rows["dim_branch"][0]["code"]
    rows["dim_bank"] = [{"code": f"ACC-{tag}", "bank_name": "Тест", "currency": "UZS"}]
    rows["fact_balance"] = [
        {"doc_type": "statement", "src_id": "o", "date_id": 20260731, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 1000},
        {"doc_type": "statement", "src_id": "c", "date_id": 20260831, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 899.5},  # |Разница| 0,5 ≤ 1% × 100
        {"doc_type": "statement", "src_id": "s", "date_id": 20260924, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 949.5},  # sentabr: +50 kirim
    ]
    assert _check(source, rows)["balance_identity"].ok


def test_balance_identity_unverifiable_new_account_excluded(source: str) -> None:
    # Reviewer ruling (opening completeness): filial ichida bitta hisob avgustdan oldin
    # qoldiqqa ega (tekshirib bo'ladi), ikkinchisi avgust o'rtasida (oldingi qoldiqsiz)
    # birinchi marta ko'rinadi — shu oy filial uchun "nachalniy qoldiq" TO'LIQ emas, shuning
    # uchun `violations`ga emas, `unverifiable`ga tushishi kerak (natija — ok).
    tag = new_tag()
    b = branch_row(tag)
    code = b["code"]
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [b],
        "dim_bank": [{"code": f"ACC1-{tag}", "bank_name": "Тест1", "currency": "UZS"},
                    {"code": f"ACC2-{tag}", "bank_name": "Тест2", "currency": "UZS"}],
        "fact_cashflow": [cash_row("c1", 20260805, code, 100)],
        "fact_balance": [
            # ACC1: davomiy hisob — avgustdan oldin (iyulda) qoldig'i bor.
            {"doc_type": "statement", "src_id": "a1-o", "date_id": 20260731, "branch_code": code,
             "bank_code": f"ACC1-{tag}", "balance": 200},
            {"doc_type": "statement", "src_id": "a1-c", "date_id": 20260831, "branch_code": code,
             "bank_code": f"ACC1-{tag}", "balance": 100},
            # ACC2: avgust o'rtasida birinchi marta ko'rinadi — nachalniy qoldiq noma'lum.
            {"doc_type": "statement", "src_id": "a2-o", "date_id": 20260815, "branch_code": code,
             "bank_code": f"ACC2-{tag}", "balance": 300},
        ],
    }
    results = _check(source, rows)
    bid = _branch_id(code)
    assert results["balance_identity"].ok
    unverifiable = results["balance_identity"].detail["unverifiable"]
    assert {"branch_id": bid, "month_id": 202608} in unverifiable
    mine = [v for v in results["balance_identity"].detail["violations"] if v["branch_id"] == bid]
    assert mine == []


def test_balance_identity_mid_month_window_uses_calendar_month(source: str) -> None:
    # R2-1: `_UNVERIFIABLE_SQL` oy chegaralarini HAQIQIY TAKVIM oyi (1-kundan) bo'yicha
    # hisoblashi kerak, hatto `window.date_from` oy o'rtasida bo'lsa ham (Task-8 inkremental
    # oynasi kabi). Hisobning BIRINCHI yozuvi 3-avgust — avgust oyi ICHIDA (1-avgustdan
    # keyin), lekin `window.date_from` 6-avgustdan boshlanadi: agar oy chegarasi xom
    # `date_from`dan hisoblansa, 3-avgust "6-avgustdan OLDIN" (demak "avvalgi qoldiq
    # mavjud") deb noto'g'ri hisoblanib, yangi hisob YASHIRIN qolib ketadi.
    tag = new_tag()
    b = branch_row(tag)
    code = b["code"]
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [b],
        "dim_bank": [{"code": f"ACC-{tag}", "bank_name": "Тест", "currency": "UZS"}],
        "fact_balance": [
            {"doc_type": "statement", "src_id": "a-o", "date_id": 20260803, "branch_code": code,
             "bank_code": f"ACC-{tag}", "balance": 100},
        ],
    }
    window = Window(date(2026, 8, 6), FULL_WINDOW.date_to)
    run_id, build_id = load_and_build(source, rows, window=window)
    with etl_transaction() as conn:
        results = {
            r.code: r for r in run_checks(conn, run_id=run_id, build_id=build_id,
                                          source=source, window=window, totals=None)
        }
    bid = _branch_id(code)
    assert results["balance_identity"].ok
    assert {"branch_id": bid, "month_id": 202608} in results["balance_identity"].detail[
        "unverifiable"]


def test_balance_identity_scoped_to_own_build(source: str) -> None:
    # M6: `mart.agg_cash_month` bir nechta build'ning qatorlarini BIRGALIKDA saqlaydi
    # (build_all — butun ombor sinovi, har safar qayta hisoblanadi) — shuning uchun eski,
    # allaqachon TUZATILGAN buzilishning "muzlagan" nusxasi jadvalda qolgan bo'lsa ham,
    # YANGI build_id faqat O'ZINING (qayta hisoblangan, allaqachon to'g'ri) qatorlarini
    # ko'rishi kerak — eski build_id'ning qatoriga aralashmasligi kerak.
    tag = new_tag()
    rows = _clean(tag)
    code = rows["dim_branch"][0]["code"]
    rows["dim_bank"] = [{"code": f"ACC-{tag}", "bank_name": "Тест", "currency": "UZS"}]
    rows["fact_balance"] = [
        {"doc_type": "statement", "src_id": "o", "date_id": 20260731, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 1000},
        # Noto'g'ri: 800 (to'g'risi 900 = 1000 − 100) — birinchi build buziladi.
        {"doc_type": "statement", "src_id": "c", "date_id": 20260831, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 800},
        {"doc_type": "statement", "src_id": "s", "date_id": 20260924, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 850},
    ]
    bad_results = _check(source, rows)
    bid = _branch_id(code)
    assert not bad_results["balance_identity"].ok

    # Xuddi shu hujjatlar (doc_type, src_id) — TO'G'RILANGAN qoldiq bilan qayta yuklanadi
    # (idempotent upsert, xuddi manba xatosi tuzatilganidek). Eski build mart jadvalida
    # o'zining (buzilgan) qatori bilan qolaveradi — u PURGE qilinmaydi.
    fixed_rows = {**rows, "fact_balance": [
        rows["fact_balance"][0],
        {"doc_type": "statement", "src_id": "c", "date_id": 20260831, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 900},
        {"doc_type": "statement", "src_id": "s", "date_id": 20260924, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 950},
    ]}
    fixed_results = _check(source, fixed_rows)
    mine = [v for v in fixed_results["balance_identity"].detail["violations"]
           if v["branch_id"] == bid]
    assert fixed_results["balance_identity"].ok
    assert mine == []


def test_missing_branch_fails_mandatory_dims(source: str) -> None:
    rows = _clean(new_tag())
    rows["fact_cashflow"].append(cash_row("x", 20260805, "NO-BRANCH", 5))
    results = _check(source, rows)
    assert not results["mandatory_dims"].ok
    assert results["mandatory_dims"].detail["logged_errors"] == 1


def test_missing_branch_key_none_fails_mandatory_dims(source: str) -> None:
    # R2-3: branch kaliti BUTUNLAY yo'q/NULL bo'lgan qator ham (nafaqat noma'lum kod)
    # mandatory_dims'ni buzishi kerak.
    tag = new_tag()
    b = branch_row(tag)
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [b],
        "fact_cashflow": [
            {"doc_type": "bank_entry", "src_id": "nb-none", "date_id": 20260805,
             "branch_code": None, "item_code": OTHER_OUT_ITEM, "direction": "out",
             "amount": 5, "gl_account": "5110"},
        ],
    }
    results = _check(source, rows)
    assert not results["mandatory_dims"].ok
    assert results["mandatory_dims"].detail["logged_errors"] == 1


def test_unknown_item_only_warns(source: str) -> None:
    rows = _clean(new_tag())
    rows["fact_cashflow"].append(
        cash_row("y", 20260805, rows["dim_branch"][0]["code"], 5, item_code="NO-ITEM"))
    results = _check(source, rows)
    assert results["mandatory_dims"].ok
    assert results["mandatory_dims"].detail["logged_warnings"] == 1


def test_capped_error_log_still_reports_blocking_code(
    source: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # I2: agar bitta partiyada `etl_error`ga yozish ERROR_LIMIT bilan cheklansa, bloklovchi
    # kodlar (masalan `missing_branch`) baribir ustuvor tartibda yozilishi va shu sababli
    # tekshiruv tomonidan ko'rilishi kerak — hatto ular sonlik jihatdan ozchilikda bo'lsa ham.
    monkeypatch.setattr(merge_module, "ERROR_LIMIT", 5)
    tag = new_tag()
    b = branch_row(tag)
    code = b["code"]
    bad_type_rows = [
        {"doc_type": "bank_entry", "src_id": f"bad{i}", "date_id": 20260805,
         "branch_code": code, "item_code": OTHER_OUT_ITEM, "direction": "out",
         "amount": "not-a-number", "gl_account": "5110"}
        for i in range(6)
    ]
    missing_branch_row = cash_row("nb1", 20260805, "NO-SUCH-BRANCH", 5)
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [b], "fact_cashflow": [*bad_type_rows, missing_branch_row],
    }
    run_id, build_id = load_and_build(source, rows)
    with etl_transaction() as conn:
        results = {
            r.code: r for r in run_checks(conn, run_id=run_id, build_id=build_id,
                                          source=source, window=FULL_WINDOW, totals=None)
        }
    assert not results["mandatory_dims"].ok
    assert results["mandatory_dims"].detail["logged_errors"] == 1


def test_generation_above_capacity_fails(source: str) -> None:
    tag = new_tag()
    rows = _clean(tag, capacity_mw=10)  # maksimum 10 × 24 = 240 MVt·soat = 0,24 mln kVt·soat
    code = rows["dim_branch"][0]["code"]
    rows["fact_generation"] = [
        {"doc_type": "askue_day", "src_id": "g1", "date_id": 20260805, "branch_code": code,
         "generation": 0.2},
        {"doc_type": "askue_day", "src_id": "g2", "date_id": 20260806, "branch_code": code,
         "generation": 0.5},
    ]
    results = _check(source, rows)
    bid = _branch_id(code)
    mine = [v for v in results["capacity_limit"].detail["violations"] if v["branch_id"] == bid]
    assert not results["capacity_limit"].ok
    assert [v["date_id"] for v in mine] == [20260806]


def test_generation_daily_sum_above_capacity_fails(source: str) -> None:
    # I1: ikkita hujjat, har biri ALOHIDA limitdan past, LEKIN sutkalik YIG'INDISI oshadi.
    tag = new_tag()
    rows = _clean(tag, capacity_mw=10)  # maksimum 0,24 mln kVt·soat
    code = rows["dim_branch"][0]["code"]
    rows["fact_generation"] = [
        {"doc_type": "askue_day", "src_id": "g1", "date_id": 20260806, "branch_code": code,
         "generation": 0.15},
        {"doc_type": "askue_day", "src_id": "g2", "date_id": 20260806, "branch_code": code,
         "generation": 0.15},  # 0,15 ikkalasi ham alohida < 0,24; jamida 0,30 > 0,24
    ]
    results = _check(source, rows)
    bid = _branch_id(code)
    mine = [v for v in results["capacity_limit"].detail["violations"] if v["branch_id"] == bid]
    assert not results["capacity_limit"].ok
    assert [v["date_id"] for v in mine] == [20260806]
    assert mine[0]["generation"] == "0.300"


def test_missing_counterparty_fails_dangling_refs(source: str) -> None:
    rows = _clean(new_tag())
    rows["fact_cashflow"].append(
        cash_row("z", 20260805, rows["dim_branch"][0]["code"], 5, cp_code="NO-CP"))
    results = _check(source, rows)
    assert not results["dangling_refs"].ok
    assert results["dangling_refs"].detail["logged_errors"] == 1


def test_run_checks_requires_scope_all(source: str) -> None:
    # M2: RLS ostidagi qisman ko'rinishda tekshiruv jimgina "ok" demasligi kerak.
    run_id, build_id = load_and_build(source, _clean(new_tag()))
    with etl_transaction() as conn:
        conn.execute(text("SELECT set_config('app.scope_all', 'off', true)"))
        with pytest.raises(RuntimeError):
            run_checks(conn, run_id=run_id, build_id=build_id, source=source,
                      window=FULL_WINDOW, totals=None)


def test_run_checks_rejects_run_id_mismatch(source: str) -> None:
    # M3: build boshqa run'ga tegishli bo'lsa yiqilishi kerak.
    run_id, build_id = load_and_build(source, _clean(new_tag()))
    with etl_transaction() as conn, pytest.raises(ValueError):
        run_checks(conn, run_id=run_id + 1, build_id=build_id, source=source,
                  window=FULL_WINDOW, totals=None)


def test_run_checks_rejects_non_building_status(source: str) -> None:
    # M3: build allaqachon 'failed' (yoki 'published'/'superseded') bo'lsa yiqilishi kerak.
    run_id, build_id = load_and_build(source, _clean(new_tag()))
    with etl_transaction() as conn:
        assert builds.mark_failed(conn, build_id)
    with etl_transaction() as conn, pytest.raises(ValueError):
        run_checks(conn, run_id=run_id, build_id=build_id, source=source,
                  window=FULL_WINDOW, totals=None)
