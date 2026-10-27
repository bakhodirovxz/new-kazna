"""S2 kredit agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

`app.dwh.aggregates` oxirida (S1 treasury_aggregates'dan keyin) import qilinadi.
Summalar kredit valyutasida (mln birlik); `outstanding` = valyutadagi qoldiq × snapshot
sanasidagi ЦБ kursi (UZS = 1; kurs yo'q → NULL, spec 4).
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

# To'lov grafigi: kredit × sana (bir sanada bir nechta qator bo'lsa — yig'indi,
# qoldiq — eng kichigi).
# date_from dan keyingi hamma qatorlar (kelajak ham) — «График погашения» va yaqin to'lovlar uchun.
_LOAN_SCHEDULE = """
INSERT INTO mart.agg_loan_schedule (build_id, branch_id, loan_id, month_id, date_id, principal_cur,
                                    interest_cur, balance_cur)
SELECT :build_id, s.branch_id, s.loan_id, d.month_id, s.date_id, sum(s.principal),
       sum(s.interest), min(s.balance)
FROM dwh.fact_loan_schedule s
JOIN dwh.dim_date d ON d.date_id = s.date_id
WHERE s.date_id >= :from_id
GROUP BY s.branch_id, s.loan_id, d.month_id, s.date_id
"""

# Oy × kredit snapshot'i (snap = oyning as_of bilan kesilgan oxirgi kuni): qoldiq — snap
# gacha oxirgi
# grafik qatorining `balance`i, qator bo'lmasa boshlang'ich summa (birinchi qatorning balance +
# principal). Qator faqat qoldiq > 0 yoki o'sha yilda to'lov bo'lsa. Stavka — dim_loan_version
# (SCD-2) snap sanasida amaldagisi.
_LOAN_MONTH = f"""
INSERT INTO mart.agg_loan_month (build_id, branch_id, month_id, loan_id, snap_date_id, loan_code,
                                 creditor, project, currency, rate, grace_until, maturity, fx_rate,
                                 original_cur, outstanding_cur, outstanding)
WITH {_MONTHS},
sched AS (
  SELECT s.loan_id, s.branch_id, s.date_id, sum(s.principal) AS principal,
         min(s.balance) AS balance
  FROM dwh.fact_loan_schedule s
  GROUP BY s.loan_id, s.branch_id, s.date_id),
first_row AS (
  SELECT DISTINCT ON (loan_id) loan_id, branch_id, balance + principal AS original
  FROM sched ORDER BY loan_id, date_id),
snap AS (
  SELECT f.loan_id, f.branch_id, f.original, m.month_id, m.end_id,
         coalesce((SELECT x.balance FROM sched x
                   WHERE x.loan_id = f.loan_id AND x.date_id <= m.end_id
                   ORDER BY x.date_id DESC LIMIT 1), f.original) AS outstanding_cur,
         EXISTS (SELECT 1 FROM sched x WHERE x.loan_id = f.loan_id
                 AND x.date_id / 10000 = m.month_id / 100) AS active_year
  FROM first_row f CROSS JOIN months m)
SELECT :build_id, s.branch_id, s.month_id, l.loan_id, s.end_id, l.code, l.creditor, l.project,
       l.currency, coalesce(v.rate, l.rate), l.grace_until, l.maturity, fx.rate, s.original,
       s.outstanding_cur, round(s.outstanding_cur * fx.rate, 2)
FROM snap s
JOIN dwh.dim_loan l ON l.loan_id = s.loan_id
JOIN dwh.dim_date dd ON dd.date_id = s.end_id
LEFT JOIN LATERAL (
  SELECT lv.rate FROM dwh.dim_loan_version lv
  WHERE lv.loan_id = l.loan_id AND lv.rate IS NOT NULL AND lv.valid_from <= dd.date
    AND (lv.valid_to IS NULL OR lv.valid_to >= dd.date)
  ORDER BY lv.valid_from DESC LIMIT 1) v ON true
LEFT JOIN LATERAL (
  SELECT CASE WHEN l.currency = 'UZS' THEN 1::numeric ELSE (
    SELECT r.rate FROM dwh.fx_rate r
    WHERE r.currency = l.currency AND r.date_id <= s.end_id
    ORDER BY r.date_id DESC LIMIT 1) END AS rate) fx ON true
WHERE s.outstanding_cur > 0 OR s.active_year
"""

LOAN_SCHEDULE = register(Aggregate("agg_loan_schedule", (_LOAN_SCHEDULE,)))
LOAN_MONTH = register(Aggregate("agg_loan_month", (_LOAN_MONTH,)))
