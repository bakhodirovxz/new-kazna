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
accounts AS (SELECT DISTINCT branch_id, bank_id FROM dwh.balance_effective),
bal AS (
  SELECT a.branch_id, m.month_id, bk.bank_name, sum(c.balance) AS closing,
         sum(p.balance) AS closing_cmp
  FROM accounts a
  CROSS JOIN months m
  JOIN dwh.dim_bank bk ON bk.bank_id = a.bank_id
  LEFT JOIN LATERAL (
    SELECT fb.balance FROM dwh.balance_effective fb
    WHERE fb.bank_id = a.bank_id AND fb.branch_id = a.branch_id AND fb.date_id <= m.end_id
    ORDER BY fb.date_id DESC LIMIT 1) c ON true
  LEFT JOIN LATERAL (
    SELECT fb.balance FROM dwh.balance_effective fb
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
FROM dwh.target_funds_effective t
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

CALENDAR_KIND_VALUES = ("taxes", "salary", "loans", "contracts")

# Shartnoma × oy: oy ichidagi eng oxirgi snapshot (oyda snapshot yo'q — shartnoma yopilgan).
_DEBT_CONTRACTS = f"""
INSERT INTO mart.agg_debt_contracts (build_id, branch_id, month_id, contract_id, contract_number,
                                     cp_name, kind, end_date, receivable, payable, overdue,
                                     overdue_days)
WITH {_MONTHS}
SELECT DISTINCT ON (f.contract_id, m.month_id)
       :build_id, f.branch_id, m.month_id, f.contract_id, c.number, cp.name, c.kind, c.end_date,
       f.receivable, f.payable, f.overdue, f.overdue_days
FROM dwh.debt_effective f
JOIN months m ON f.date_id BETWEEN m.first_id AND m.end_id
JOIN dwh.dim_contract c ON c.contract_id = f.contract_id
JOIN dwh.dim_counterparty cp ON cp.cp_id = c.cp_id
WHERE f.date_id BETWEEN :from_id AND :as_of_id
ORDER BY f.contract_id, m.month_id, f.date_id DESC
"""

_DEBT_MONTH = """
INSERT INTO mart.agg_debt_month (build_id, branch_id, month_id, receivable, payable,
                                 overdue_receivable, overdue_payable, contracts)
SELECT :build_id, coalesce(branch_id, 0), month_id, sum(receivable), sum(payable),
       coalesce(sum(overdue) FILTER (WHERE kind = 'receivable'), 0),
       coalesce(sum(overdue) FILTER (WHERE kind = 'payable'), 0), count(*)
FROM mart.agg_debt_contracts
WHERE build_id = :build_id AND month_id >= :from_month
GROUP BY GROUPING SETS ((branch_id, month_id), (month_id))
"""

# as_of+1 … as_of+14: reja jadvali (doc_type = payment_schedule) statya turi bo'yicha + kredit
# grafigi (valyuta × as_of gacha oxirgi kurs). Filialda oyna ichida grafik bo'lsa, "loans" turi
# faqat grafikdan (ikki marta sanalmaydi). Har filial × kun × tur uchun qator (nol ham) — as_of
# har doim aniqlanadi.
_CALENDAR = """
INSERT INTO mart.agg_calendar_day (build_id, branch_id, month_id, as_of_id, date_id, kind, amount)
WITH days AS (
  SELECT date_id FROM dwh.dim_date
  WHERE date > CAST(:as_of AS date) AND date <= CAST(:as_of AS date) + 14),
kinds AS (SELECT unnest(ARRAY['taxes', 'salary', 'loans', 'contracts']) AS kind),
cfg AS (SELECT CAST(:calendar_kinds AS jsonb) AS v),
item_kind AS (
  SELECT i.item_id, CASE
      WHEN i.code IN (SELECT jsonb_array_elements_text(coalesce(v->'taxes', '[]')) FROM cfg)
        THEN 'taxes'
      WHEN i.code IN (SELECT jsonb_array_elements_text(coalesce(v->'salary', '[]')) FROM cfg)
        THEN 'salary'
      WHEN i.code IN (SELECT jsonb_array_elements_text(coalesce(v->'loans', '[]')) FROM cfg)
        THEN 'loans'
      ELSE 'contracts' END AS kind
  FROM dwh.dim_item i WHERE i.direction = 'out'),
plan AS (
  SELECT p.branch_id, p.date_id, ik.kind, sum(p.amount) AS amount
  FROM dwh.payment_plan_effective p
  JOIN item_kind ik ON ik.item_id = p.item_id
  JOIN days d ON d.date_id = p.date_id
  WHERE p.doc_type = :schedule_doc_type
  GROUP BY p.branch_id, p.date_id, ik.kind),
loan AS (
  SELECT s.branch_id, s.date_id,
         sum((s.principal + s.interest)
             * CASE WHEN l.currency = 'UZS' THEN 1 ELSE fx.rate END) AS amount
  FROM dwh.loan_schedule_effective s
  JOIN days d ON d.date_id = s.date_id
  JOIN dwh.dim_loan l ON l.loan_id = s.loan_id
  LEFT JOIN LATERAL (
    SELECT r.rate FROM dwh.fx_rate r
    WHERE r.currency = l.currency AND r.date_id <= :as_of_id
    ORDER BY r.date_id DESC LIMIT 1) fx ON true
  GROUP BY s.branch_id, s.date_id),
src AS (
  SELECT branch_id, date_id, kind, amount FROM plan
  WHERE kind <> 'loans' OR branch_id NOT IN (SELECT branch_id FROM loan)
  UNION ALL
  SELECT branch_id, date_id, 'loans', amount FROM loan),
grid AS (
  SELECT b.branch_id, d.date_id, k.kind
  FROM dwh.dim_branch b CROSS JOIN days d CROSS JOIN kinds k)
SELECT :build_id, coalesce(g.branch_id, 0),
       CAST(to_char(CAST(:as_of AS date), 'YYYYMM') AS integer), :as_of_id, g.date_id, g.kind,
       coalesce(sum(s.amount), 0)
FROM grid g
LEFT JOIN src s ON s.branch_id = g.branch_id AND s.date_id = g.date_id AND s.kind = g.kind
GROUP BY GROUPING SETS ((g.branch_id, g.date_id, g.kind), (g.date_id, g.kind))
"""

DEBT_CONTRACTS = register(Aggregate("agg_debt_contracts", (_DEBT_CONTRACTS,)))
DEBT_MONTH = register(Aggregate("agg_debt_month", (_DEBT_MONTH,)))
CALENDAR_DAY = register(Aggregate("agg_calendar_day", (_CALENDAR,)))
