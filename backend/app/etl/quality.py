"""Sifat tekshiruvlari (spec 5.3, TZ 3). Istalgan buzilish → failed_quality, publish yo'q.

1. control_totals   — fact_cashflow oylik summasi = manba nazorat summasi (5110/5210/5530) ±0,1%
2. balance_identity — konechniy = nachalniy + ЧДП + Разница, |Разница| ≤ 1% oborot
3. mandatory_dims   — filial majburiy (statyasiz → «Прочие» + ogohlantirish, xato emas)
4. capacity_limit   — sutkalik ishlab chiqarish (BARCHA hujjatlar yig'indisi) ≤ quvvat × 24
5. dangling_refs    — mavjud bo'lmagan o'lchovga havola yo'q (FK + etl_error hisoboti)

Fix round 1 (task-7-findings-r1.md):
- I2: `core.etl_error`ga yozish `app/etl/merge.py`da ERROR_LIMIT bilan cheklangan — shu sabab
  `mandatory_dims`/`dangling_refs` detail'idagi sonlar XOM (staging bosqichidagi) emas, balki
  YOZILGAN (cheklangan) qatorlar soni — kalit nomlari shuni aks ettirish uchun ataylab
  `logged_errors`/`logged_warnings` deb nomlangan (haqiqiy `log_capped` bayrog'i uchun
  `MergeStats` qayerdadir saqlanishi kerak edi — bu reja doirasida saqlanmaydi, shuning uchun
  hujjatlashtirish + nomlash orqali hal qilingan, controller ruling'iga muvofiq). Bloklovchi
  kodlar (`missing_branch`, `missing_dim`) cheklov ostida ham HAR DOIM birinchi navbatda
  yoziladi (`merge.py`dagi ORDER BY ustuvorligi) — shu sababli ular hech qachon "yo'qolib
  ketmaydi", faqat ularning umumiy soni cheklangan bo'lishi mumkin.
- M2/M3: `run_checks` chaqiruvchi konteksti (RLS scope, build/run mosligi) haqida qat'iy
  taxminlar qiladi — noto'g'ri chaqirilsa jim noto'g'ri "ok" qaytarish o'rniga yiqiladi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.etl.types import ControlTotals, Window

CHECK_CODES = ("control_totals", "balance_identity", "mandatory_dims", "capacity_limit",
               "dangling_refs")
CONTROL_TOLERANCE = Decimal("0.001")
BALANCE_TOLERANCE = Decimal("0.01")
SAMPLE = 50


@dataclass(frozen=True, slots=True)
class CheckResult:
    code: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


def failed(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.ok]


def _control_totals(conn: Connection, source: str, window: Window,
                    totals: ControlTotals | None) -> CheckResult:
    if totals is None:
        return CheckResult("control_totals", True, {"skipped": True})
    ours = {
        int(m): Decimal(v)
        for m, v in conn.execute(
            text("SELECT d.month_id, sum(f.amount) FROM dwh.fact_cashflow f "
                 "JOIN dwh.dim_date d ON d.date_id = f.date_id "
                 "WHERE f.src_system = :s AND f.date_id BETWEEN :f AND :t GROUP BY d.month_id"),
            {"s": source, "f": window.from_id, "t": window.to_id},
        ).all()
    }
    # M5: oynadan tashqaridagi manba oylari e'tiborsiz qoldiriladi (mos kelmaslikka
    # hisoblanmaydi) — ular alohida `ignored_months`da ro'yxatga olinadi.
    valid_months = set(window.month_ids())
    ignored_months = sorted(m for m in totals.cashflow_by_month if m not in valid_months)
    mismatches = []
    for month in sorted((set(ours) | set(totals.cashflow_by_month)) & valid_months):
        expected = Decimal(totals.cashflow_by_month.get(month, Decimal(0)))
        actual = ours.get(month, Decimal(0))
        if abs(actual - expected) > abs(expected) * CONTROL_TOLERANCE:
            mismatches.append({"month": month, "source": str(expected), "dwh": str(actual)})
    return CheckResult("control_totals", not mismatches,
                       {"mismatches": mismatches[:SAMPLE], "ignored_months": ignored_months})


# M1 (opening completeness, reviewer ruling): agar biror hisob oy ichida BIRINCHI MARTA
# ko'rinsa (oy boshidan OLDIN unga tegishli hech qanday qoldiq yozuvi yo'q), o'sha
# filial-oy uchun "nachalniy qoldiq" TO'LIQ emas (yangi hisob ulushi tushib qoladi) — bunday
# filial-oylar tekshirib bo'lmaydi (`unverifiable`) va `violations`dan chiqarib tashlanadi.
# Bu Task-6 agregatlarini o'zgartirmaydi — bevosita `dwh.fact_balance`ga so'rov beriladi.
_UNVERIFIABLE_SQL = text(
    "WITH months AS (\n"
    "  SELECT month_id, min(date_id) AS first_id, max(date_id) AS end_id\n"
    "  FROM dwh.dim_date WHERE date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)\n"
    "  GROUP BY month_id),\n"
    "in_month AS (\n"
    "  SELECT DISTINCT fb.branch_id, m.month_id, fb.bank_id\n"
    "  FROM dwh.fact_balance fb JOIN months m ON fb.date_id BETWEEN m.first_id AND m.end_id),\n"
    "before_month AS (\n"
    "  SELECT DISTINCT fb.branch_id, fb.bank_id, m.month_id\n"
    "  FROM dwh.fact_balance fb JOIN months m ON fb.date_id < m.first_id)\n"
    "SELECT DISTINCT im.branch_id, im.month_id FROM in_month im\n"
    "LEFT JOIN before_month bm ON bm.branch_id = im.branch_id AND bm.bank_id = im.bank_id\n"
    "  AND bm.month_id = im.month_id\n"
    "WHERE bm.bank_id IS NULL\n"
    "ORDER BY im.month_id, im.branch_id"
)


def _balance_identity(conn: Connection, build_id: int, window: Window) -> CheckResult:
    months = window.month_ids()
    unverifiable = [
        {"branch_id": r.branch_id, "month_id": r.month_id}
        for r in conn.execute(_UNVERIFIABLE_SQL,
                              {"date_from": window.date_from, "date_to": window.date_to}).all()
    ]
    skip = {(u["branch_id"], u["month_id"]) for u in unverifiable}
    rows = conn.execute(
        text("SELECT branch_id, month_id, diff, inflow + outflow AS turnover "
             "FROM mart.agg_cash_month WHERE build_id = :b AND item_id = 0 AND branch_id <> 0 "
             "AND month_id BETWEEN :mf AND :mt AND opening_balance IS NOT NULL "
             "AND closing_balance IS NOT NULL "
             "AND abs(diff) > greatest(:tol * (inflow + outflow), 0.01) "
             "ORDER BY month_id, branch_id"),
        {"b": build_id, "mf": months[0], "mt": months[-1], "tol": BALANCE_TOLERANCE},
    ).all()
    violations = [{"branch_id": r.branch_id, "month_id": r.month_id, "diff": str(r.diff),
                   "turnover": str(r.turnover)} for r in rows
                  if (r.branch_id, r.month_id) not in skip]
    return CheckResult("balance_identity", not violations,
                       {"violations": violations[:SAMPLE], "unverifiable": unverifiable[:SAMPLE]})


def _error_counts(conn: Connection, run_id: int) -> dict[str, int]:
    # M4: faqat bloklovchi ('error') darajadagi kodlar — 'warning' bu yerda YO'Q, ularni
    # `_warning_counts` alohida hisoblaydi (bitta severity aralashmasin).
    return {
        code: int(n)
        for code, n in conn.execute(
            text("SELECT code, count(*) FROM core.etl_error "
                 "WHERE run_id = :r AND severity = 'error' GROUP BY code"),
            {"r": run_id},
        ).all()
    }


def _warning_counts(conn: Connection, run_id: int) -> dict[str, int]:
    return {
        code: int(n)
        for code, n in conn.execute(
            text("SELECT code, count(*) FROM core.etl_error "
                 "WHERE run_id = :r AND severity = 'warning' GROUP BY code"),
            {"r": run_id},
        ).all()
    }


def _capacity(conn: Connection, window: Window) -> CheckResult:
    # I1: sutkalik chegara BITTA hujjatga emas, filial+sana+manba KESIMIDAGI YIG'INDIGA
    # nisbatan tekshiriladi (bir nechta hujjat alohida limitdan past, jamida oshib ketishi
    # mumkin) — har bir manba (`src_system`) alohida hisoblanadi (bir branch-kunga ikki xil
    # manba qo'sh hisoblanmasin). generation — mln kVt·soat; ×1000 = MVt·soat;
    # chegara capacity_mw × 24.
    rows = conn.execute(
        text("WITH daily AS (\n"
             "  SELECT g.branch_id, g.date_id, g.src_system, sum(g.generation) AS generation\n"
             "  FROM dwh.fact_generation g\n"
             "  WHERE g.date_id BETWEEN :f AND :t\n"
             "  GROUP BY g.branch_id, g.date_id, g.src_system)\n"
             "SELECT d.branch_id, d.date_id, d.generation, v.capacity_mw\n"
             "FROM daily d\n"
             "JOIN dwh.dim_date dt ON dt.date_id = d.date_id\n"
             "JOIN dwh.dim_branch_version v ON v.branch_id = d.branch_id\n"
             "  AND dt.date >= v.valid_from AND (v.valid_to IS NULL OR dt.date <= v.valid_to)\n"
             "WHERE v.capacity_mw IS NOT NULL AND d.generation * 1000 > v.capacity_mw * 24\n"
             "ORDER BY d.date_id, d.branch_id\n"
             "LIMIT :n"),
        {"f": window.from_id, "t": window.to_id, "n": SAMPLE},
    ).all()
    violations = [{"branch_id": r.branch_id, "date_id": r.date_id,
                   "generation": str(r.generation), "capacity_mw": str(r.capacity_mw)}
                  for r in rows]
    return CheckResult("capacity_limit", not violations, {"violations": violations})


def run_checks(conn: Connection, *, run_id: int, build_id: int, source: str, window: Window,
               totals: ControlTotals | None) -> list[CheckResult]:
    # M2: RLS ostida "hamma narsa toza" degan noto'g'ri signal berish o'rniga — agar bu
    # tranzaksiya `ugk_etl`ning `app.scope_all = 'on'` doirasida bo'lmasa (masalan, oddiy
    # `ugk_app` yoki filial-cheklangan ulanish), tekshiruvlar filiallarga bo'lingan ma'lumotni
    # QISMAN ko'rishi mumkin va bu jimgina "ok" deb noto'g'ri hisobot berardi — shu sabab
    # fail-closed.
    scope = conn.execute(
        text("SELECT current_setting('app.scope_all', true)")).scalar_one_or_none()
    if scope != "on":
        raise RuntimeError(
            "run_checks: 'app.scope_all' = 'on' kutilgan edi (RLS ostida to'liq ko'rinish "
            "kerak) — noto'g'ri konteksitda chaqirilgan")
    # M3: `build_id` aynan shu `run_id` yuklashiga tegishli va hali nashr qilinmagan
    # ('building' yoki 'ready') bo'lishi kerak — aks holda (masalan, boshqa yuklashning
    # build'i yoki allaqachon 'published'/'superseded'/'failed') tekshiruv natijasi
    # ma'nosiz yoki chalg'ituvchi bo'ladi.
    build = conn.execute(
        text("SELECT load_id, status FROM core.builds WHERE build_id = :b"),
        {"b": build_id}).one_or_none()
    if build is None or build.load_id != run_id or build.status not in ("building", "ready"):
        raise ValueError(
            f"run_checks: build {build_id} run_id={run_id}ga tegishli emas yoki holati "
            "'building'/'ready' emas")

    errors = _error_counts(conn, run_id)
    warnings = _warning_counts(conn, run_id)
    missing_branch = errors.get("missing_branch", 0)
    missing_dim = errors.get("missing_dim", 0)
    missing_item = warnings.get("missing_item", 0)
    return [
        _control_totals(conn, source, window, totals),
        _balance_identity(conn, build_id, window),
        CheckResult("mandatory_dims", missing_branch == 0,
                    {"logged_errors": missing_branch, "logged_warnings": missing_item}),
        _capacity(conn, window),
        # FK'lar DEFERRABLE — noto'g'ri havola commit'ga yetib bormaydi; merge ularni
        # etl_error'ga yozib o'tkazib yuboradi. Shu yerda hisobot bo'yicha yuklash yiqiladi.
        CheckResult("dangling_refs", missing_dim == 0, {"logged_errors": missing_dim}),
    ]
