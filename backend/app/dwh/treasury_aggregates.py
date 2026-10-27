"""S1 g'aznachilik agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

`app.dwh.aggregates` modulining oxirida import qilinadi, shuning uchun build_all tartibi:
2-reja agregatlari → shu fayldagilar (ro'yxatdan o'tish tartibida). Parametrlar
`BuildParams.bind` dan: :build_id, :from_id, :as_of_id, :cmp_day, :from_month, :as_of.
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

NO_BANK = "Банк не указан"

_CASH_BANK = f"""
INSERT INTO mart.agg_cash_bank_month (build_id, branch_id, month_id, bank_name, inflow, outflow,
                                      closing_balance, closing_cmp)
WITH {_MONTHS},
flows AS (
  SELECT f.branch_id, d.month_id, coalesce(b.bank_name, '{NO_BANK}') AS bank_name,
         coalesce(sum(f.amount) FILTER (WHERE f.direction = 'in'), 0) AS inflow,
         coalesce(sum(f.amount) FILTER (WHERE f.direction = 'out'), 0) AS outflow
  FROM dwh.fact_cashflow f
  JOIN dwh.dim_date d ON d.date_id = f.date_id
  JOIN months m ON m.month_id = d.month_id
  LEFT JOIN dwh.dim_bank b ON b.bank_id = f.bank_id
  WHERE f.date_id BETWEEN :from_id AND :as_of_id
  GROUP BY f.branch_id, d.month_id, coalesce(b.bank_name, '{NO_BANK}')),
accounts AS (SELECT DISTINCT branch_id, bank_id FROM dwh.fact_balance),
bal AS (
  SELECT a.branch_id, m.month_id, bk.bank_name, sum(c.balance) AS closing,
         sum(p.balance) AS closing_cmp
  FROM accounts a
  CROSS JOIN months m
  JOIN dwh.dim_bank bk ON bk.bank_id = a.bank_id
  LEFT JOIN LATERAL (
    SELECT fb.balance FROM dwh.fact_balance fb
    WHERE fb.bank_id = a.bank_id AND fb.branch_id = a.branch_id AND fb.date_id <= m.end_id
    ORDER BY fb.date_id DESC LIMIT 1) c ON true
  LEFT JOIN LATERAL (
    SELECT fb.balance FROM dwh.fact_balance fb
    WHERE fb.bank_id = a.bank_id AND fb.branch_id = a.branch_id
      AND fb.date_id <= LEAST(m.end_id, m.first_id + :cmp_day - 1)
    ORDER BY fb.date_id DESC LIMIT 1) p ON true
  GROUP BY a.branch_id, m.month_id, bk.bank_name),
j AS (
  SELECT coalesce(f.branch_id, b.branch_id) AS branch_id,
         coalesce(f.month_id, b.month_id) AS month_id,
         coalesce(f.bank_name, b.bank_name) AS bank_name,
         coalesce(f.inflow, 0) AS inflow, coalesce(f.outflow, 0) AS outflow,
         b.closing, b.closing_cmp
  FROM flows f FULL JOIN bal b
    ON b.branch_id = f.branch_id AND b.month_id = f.month_id AND b.bank_name = f.bank_name
  WHERE f.branch_id IS NOT NULL OR b.closing IS NOT NULL OR b.closing_cmp IS NOT NULL)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, j.bank_name, sum(j.inflow),
       sum(j.outflow), sum(j.closing), sum(j.closing_cmp)
FROM j
GROUP BY GROUPING SETS ((j.branch_id, j.month_id, j.bank_name), (j.month_id, j.bank_name))
"""

_ORDERS = f"""
INSERT INTO mart.agg_payment_orders_month (build_id, branch_id, month_id, status, doc_count,
                                           amount)
WITH {_MONTHS}
SELECT :build_id, coalesce(o.branch_id, 0), d.month_id, o.status, count(*), sum(o.amount)
FROM dwh.fact_payment_order o
JOIN dwh.dim_date d ON d.date_id = o.date_id
JOIN months m ON m.month_id = d.month_id
WHERE o.date_id BETWEEN :from_id AND :as_of_id
GROUP BY GROUPING SETS ((o.branch_id, d.month_id, o.status), (d.month_id, o.status))
"""

_FUNDS = f"""
INSERT INTO mart.agg_target_funds_month (build_id, branch_id, month_id, source_id, source_name,
                                         allocated, used)
WITH {_MONTHS}
SELECT :build_id, coalesce(t.branch_id, 0), d.month_id, t.source_id, s.name, sum(t.allocated),
       sum(t.used)
FROM dwh.fact_target_funds t
JOIN dwh.dim_date d ON d.date_id = t.date_id
JOIN months m ON m.month_id = d.month_id
JOIN dwh.dim_source s ON s.source_id = t.source_id
WHERE t.date_id BETWEEN :from_id AND :as_of_id
GROUP BY GROUPING SETS ((t.branch_id, d.month_id, t.source_id, s.name),
                        (d.month_id, t.source_id, s.name))
"""

CASH_BANK_MONTH = register(Aggregate("agg_cash_bank_month", (_CASH_BANK,)))
PAYMENT_ORDERS_MONTH = register(Aggregate("agg_payment_orders_month", (_ORDERS,)))
TARGET_FUNDS_MONTH = register(Aggregate("agg_target_funds_month", (_FUNDS,)))
