"""Sifat tekshiruvlari (spec 5.3, TZ 3). Istalgan buzilish → failed_quality, publish yo'q.

1. control_totals   — fact_cashflow oylik summasi = manba nazorat summasi (5110/5210/5530) ±0,1%
2. balance_identity — konechniy = nachalniy + ЧДП + Разница, |Разница| ≤ 1% oborot
3. mandatory_dims   — filial majburiy (statyasiz → «Прочие» + ogohlantirish, xato emas)
4. capacity_limit   — sutkalik ishlab chiqarish ≤ quvvat × 24
5. dangling_refs    — mavjud bo'lmagan o'lchovga havola yo'q (FK + etl_error hisoboti)
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
    mismatches = []
    for month in sorted(set(ours) | set(totals.cashflow_by_month)):
        expected = Decimal(totals.cashflow_by_month.get(month, Decimal(0)))
        actual = ours.get(month, Decimal(0))
        if abs(actual - expected) > abs(expected) * CONTROL_TOLERANCE:
            mismatches.append({"month": month, "source": str(expected), "dwh": str(actual)})
    return CheckResult("control_totals", not mismatches, {"mismatches": mismatches[:SAMPLE]})


def _balance_identity(conn: Connection, build_id: int, window: Window) -> CheckResult:
    months = window.month_ids()
    rows = conn.execute(
        text("SELECT branch_id, month_id, diff, inflow + outflow AS turnover "
             "FROM mart.agg_cash_month WHERE build_id = :b AND item_id = 0 AND branch_id <> 0 "
             "AND month_id BETWEEN :mf AND :mt AND opening_balance IS NOT NULL "
             "AND closing_balance IS NOT NULL "
             "AND abs(diff) > greatest(:tol * (inflow + outflow), 0.01) "
             "ORDER BY month_id, branch_id LIMIT :n"),
        {"b": build_id, "mf": months[0], "mt": months[-1], "tol": BALANCE_TOLERANCE, "n": SAMPLE},
    ).all()
    violations = [{"branch_id": r.branch_id, "month_id": r.month_id, "diff": str(r.diff),
                   "turnover": str(r.turnover)} for r in rows]
    return CheckResult("balance_identity", not violations, {"violations": violations})


def _error_counts(conn: Connection, run_id: int) -> dict[str, int]:
    return {
        code: int(n)
        for code, n in conn.execute(
            text("SELECT code, count(*) FROM core.etl_error WHERE run_id = :r GROUP BY code"),
            {"r": run_id},
        ).all()
    }


def _capacity(conn: Connection, window: Window) -> CheckResult:
    # generation — mln kVt·soat; ×1000 = MVt·soat; chegara capacity_mw × 24.
    rows = conn.execute(
        text("SELECT g.branch_id, g.date_id, g.generation, v.capacity_mw "
             "FROM dwh.fact_generation g "
             "JOIN dwh.dim_date d ON d.date_id = g.date_id "
             "JOIN dwh.dim_branch_version v ON v.branch_id = g.branch_id "
             "AND d.date >= v.valid_from AND (v.valid_to IS NULL OR d.date <= v.valid_to) "
             "WHERE g.date_id BETWEEN :f AND :t AND v.capacity_mw IS NOT NULL "
             "AND g.generation * 1000 > v.capacity_mw * 24 "
             "ORDER BY g.date_id, g.branch_id LIMIT :n"),
        {"f": window.from_id, "t": window.to_id, "n": SAMPLE},
    ).all()
    violations = [{"branch_id": r.branch_id, "date_id": r.date_id,
                   "generation": str(r.generation), "capacity_mw": str(r.capacity_mw)}
                  for r in rows]
    return CheckResult("capacity_limit", not violations, {"violations": violations})


def run_checks(conn: Connection, *, run_id: int, build_id: int, source: str, window: Window,
               totals: ControlTotals | None) -> list[CheckResult]:
    counts = _error_counts(conn, run_id)
    missing_branch = counts.get("missing_branch", 0)
    missing_dim = counts.get("missing_dim", 0)
    return [
        _control_totals(conn, source, window, totals),
        _balance_identity(conn, build_id, window),
        CheckResult("mandatory_dims", missing_branch == 0,
                    {"errors": missing_branch, "warnings": counts.get("missing_item", 0)}),
        _capacity(conn, window),
        # FK'lar DEFERRABLE — noto'g'ri havola commit'ga yetib bormaydi; merge ularni
        # etl_error'ga yozib o'tkazib yuboradi. Shu yerda hisobot bo'yicha yuklash yiqiladi.
        CheckResult("dangling_refs", missing_dim == 0, {"errors": missing_dim}),
    ]
