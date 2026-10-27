"""Oylik agregatlar freymvorki (spec 4.7). Keyingi rejalar yangi oila qo'shganda bitta
`register(Aggregate(...))` yozadi: jadval + tartiblangan SQL'lar. Parametrlar:
:build_id, :as_of, :date_from, :from_id, :as_of_id, :cmp_day, :from_month, :keep_month.

Saqlash (spec 4.7): faktlar 5 yil, agregatlar 10 yil — `date_from` dan oldingi oylar
(faktlari o'chirilgan) yangi build'ga oldingi aktiv build'dan ko'chiriladi.

UI faqat shu agregatlarni (pub view orqali) o'qiydi — faktlarga so'rov yubormaydi (TZ 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh.dates import date_id, month_id, month_start


@dataclass(frozen=True, slots=True)
class Aggregate:
    table: str  # mart sxemasidagi jadval
    statements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildParams:
    as_of: date
    date_from: date
    keep_from: date | None = None  # agregatlar saqlanadigan eng eski sana (10 yil)

    def bind(self, build_id: int) -> dict[str, Any]:
        return {
            "build_id": build_id,
            "as_of": self.as_of,
            "date_from": self.date_from,
            # Fix r1 (M5): oy boshiga normallashtirilgan — aks holda `date_from` oyning
            # o'rtasida bo'lsa, o'sha OYNING boshidan `date_from`gacha bo'lgan kunlar
            # faktlardan (`WHERE f.date_id BETWEEN :from_id AND :as_of_id`) chiqarib
            # tashlanib, birinchi oy kesilib qolardi.
            "from_id": date_id(month_start(self.date_from)),
            "as_of_id": date_id(self.as_of),
            "cmp_day": self.as_of.day,
            "from_month": month_id(self.date_from),
            "keep_month": month_id(self.keep_from or self.date_from),
        }


AGGREGATES: list[Aggregate] = []


def register(aggregate: Aggregate) -> Aggregate:
    if any(a.table == aggregate.table for a in AGGREGATES):
        raise ValueError(f"agregat allaqachon ro'yxatda: {aggregate.table}")
    AGGREGATES.append(aggregate)
    return aggregate


# Faktlari yo'q eski oylar: aktiv build qatorlari build_id almashtirilib ko'chiriladi.
_CARRY_FORWARD = (
    "INSERT INTO mart.{table} SELECT (jsonb_populate_record(NULL::mart.{table}, "
    "to_jsonb(a) || jsonb_build_object('build_id', :build_id))).* FROM mart.{table} a "
    "WHERE a.build_id = (SELECT active_build_id FROM core.data_version WHERE id = 1) "
    "AND a.month_id < :from_month AND a.month_id >= :keep_month"
)


def build_all(conn: Connection, build_id: int, params: BuildParams) -> dict[str, int]:
    bound = params.bind(build_id)
    out: dict[str, int] = {}
    for aggregate in AGGREGATES:
        # nosemgrep: avoid-sqlalchemy-text
        carried = conn.execute(text(_CARRY_FORWARD.format(table=aggregate.table)),
                               bound).rowcount
        out[aggregate.table] = carried + sum(
            conn.execute(text(sql), bound).rowcount for sql in aggregate.statements
        )
    return out


# Davr oylari: days = as_of gacha bo'lgan kunlar (yopilmagan oy uchun haqiqiy kunlar).
_MONTHS = """months AS (
  SELECT month_id, min(date_id) AS first_id, max(date_id) AS end_id, count(*)::smallint AS days
  FROM dwh.dim_date WHERE date BETWEEN CAST(:date_from AS date) AND CAST(:as_of AS date)
  GROUP BY month_id)"""

_CASH_ITEMS = f"""
INSERT INTO mart.agg_cash_month (build_id, branch_id, month_id, item_id, inflow, outflow,
                                 inflow_cmp, outflow_cmp, days_in_period)
WITH {_MONTHS}
SELECT :build_id, coalesce(x.branch_id, 0), x.month_id, x.item_id, sum(x.inflow),
       sum(x.outflow), sum(x.inflow_cmp), sum(x.outflow_cmp), max(x.days)
FROM (
  SELECT f.branch_id, d.month_id, f.item_id, m.days,
         CASE WHEN f.direction = 'in' THEN f.amount ELSE 0 END AS inflow,
         CASE WHEN f.direction = 'out' THEN f.amount ELSE 0 END AS outflow,
         CASE WHEN f.direction = 'in' AND d.day <= :cmp_day THEN f.amount ELSE 0 END AS inflow_cmp,
         CASE WHEN f.direction = 'out' AND d.day <= :cmp_day THEN f.amount ELSE 0 END AS outflow_cmp
  FROM dwh.fact_cashflow f
  JOIN dwh.dim_date d ON d.date_id = f.date_id
  JOIN months m ON m.month_id = d.month_id
  WHERE f.date_id BETWEEN :from_id AND :as_of_id
) x
GROUP BY GROUPING SETS ((x.branch_id, x.month_id, x.item_id), (x.month_id, x.item_id))
"""

# Filial × oy jami qatori (item_id = 0): oqimlar + hisob bo'yicha oxirgi qoldiqlar yig'indisi.
_CASH_TOTALS = f"""
INSERT INTO mart.agg_cash_month (build_id, branch_id, month_id, item_id, inflow, outflow,
                                 inflow_cmp, outflow_cmp, days_in_period, opening_balance,
                                 closing_balance, diff)
WITH {_MONTHS},
flows AS (
  SELECT branch_id, month_id, sum(inflow) AS inflow, sum(outflow) AS outflow,
         sum(inflow_cmp) AS inflow_cmp, sum(outflow_cmp) AS outflow_cmp
  FROM mart.agg_cash_month
  WHERE build_id = :build_id AND branch_id <> 0 AND item_id <> 0 AND month_id >= :from_month
  GROUP BY branch_id, month_id),
bal AS (
  SELECT b.branch_id, m.month_id, m.days, ob.total AS opening, cb.total AS closing
  FROM dwh.dim_branch b
  CROSS JOIN months m
  LEFT JOIN LATERAL (
    SELECT sum(z.balance) AS total FROM (
      SELECT DISTINCT ON (fb.bank_id) fb.balance FROM dwh.fact_balance fb
      WHERE fb.branch_id = b.branch_id AND fb.date_id < m.first_id
      ORDER BY fb.bank_id, fb.date_id DESC) z) ob ON true
  LEFT JOIN LATERAL (
    SELECT sum(z.balance) AS total FROM (
      SELECT DISTINCT ON (fb.bank_id) fb.balance FROM dwh.fact_balance fb
      WHERE fb.branch_id = b.branch_id AND fb.date_id <= m.end_id
      ORDER BY fb.bank_id, fb.date_id DESC) z) cb ON true)
SELECT :build_id, bal.branch_id, bal.month_id, 0, coalesce(f.inflow, 0), coalesce(f.outflow, 0),
       coalesce(f.inflow_cmp, 0), coalesce(f.outflow_cmp, 0), bal.days, bal.opening, bal.closing,
       bal.closing - (bal.opening + coalesce(f.inflow, 0) - coalesce(f.outflow, 0))
FROM bal LEFT JOIN flows f ON f.branch_id = bal.branch_id AND f.month_id = bal.month_id
WHERE f.branch_id IS NOT NULL OR bal.closing IS NOT NULL
"""

_CASH_ALL = """
INSERT INTO mart.agg_cash_month (build_id, branch_id, month_id, item_id, inflow, outflow,
                                 inflow_cmp, outflow_cmp, days_in_period, opening_balance,
                                 closing_balance, diff)
SELECT :build_id, 0, month_id, 0, sum(inflow), sum(outflow), sum(inflow_cmp), sum(outflow_cmp),
       max(days_in_period), sum(opening_balance), sum(closing_balance), sum(diff)
FROM mart.agg_cash_month
WHERE build_id = :build_id AND item_id = 0 AND branch_id <> 0 AND month_id >= :from_month
GROUP BY month_id
"""

_PAYMENTS = f"""
INSERT INTO mart.agg_payments_month (build_id, branch_id, month_id, item_id, plan_amount,
                                     fact_amount, fact_cmp, days_in_period)
WITH {_MONTHS},
plan AS (
  SELECT p.branch_id, d.month_id, p.item_id, sum(p.amount) AS amount
  FROM dwh.fact_payment_plan p
  JOIN dwh.dim_date d ON d.date_id = p.date_id
  JOIN months m ON m.month_id = d.month_id
  WHERE p.doc_type <> 'payment_schedule'
  GROUP BY p.branch_id, d.month_id, p.item_id),
fact AS (
  SELECT f.branch_id, d.month_id, f.item_id, sum(f.amount) AS amount,
         sum(f.amount) FILTER (WHERE d.day <= :cmp_day) AS cmp
  FROM dwh.fact_cashflow f
  JOIN dwh.dim_date d ON d.date_id = f.date_id
  JOIN months m ON m.month_id = d.month_id
  WHERE f.direction = 'out' AND f.date_id BETWEEN :from_id AND :as_of_id
  GROUP BY f.branch_id, d.month_id, f.item_id),
j AS (
  SELECT coalesce(p.branch_id, f.branch_id) AS branch_id,
         coalesce(p.month_id, f.month_id) AS month_id,
         coalesce(p.item_id, f.item_id) AS item_id,
         coalesce(p.amount, 0) AS plan_amount, coalesce(f.amount, 0) AS fact_amount,
         coalesce(f.cmp, 0) AS fact_cmp
  FROM plan p FULL JOIN fact f
    ON f.branch_id = p.branch_id AND f.month_id = p.month_id AND f.item_id = p.item_id)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, j.item_id, sum(j.plan_amount),
       sum(j.fact_amount), sum(j.fact_cmp), max(m.days)
FROM j JOIN months m ON m.month_id = j.month_id
GROUP BY GROUPING SETS ((j.branch_id, j.month_id, j.item_id), (j.month_id, j.item_id))
"""

CASH_MONTH = register(Aggregate("agg_cash_month", (_CASH_ITEMS, _CASH_TOTALS, _CASH_ALL)))
PAYMENTS_MONTH = register(Aggregate("agg_payments_month", (_PAYMENTS,)))
