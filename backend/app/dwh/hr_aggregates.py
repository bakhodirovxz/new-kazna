"""S4 kadrlar agregati (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

fact_hr — filial × lavozim × oy snapshot'i (TZ 3): штат/факт — oydagi eng oxirgi sana qatorlari
(oy ichidagi oldingi snapshot'lar tashlanadi), qabul/bo'shatish/soatlar — oy yig'indisi.
Toifa = dim_position.category. Shaxsiy ma'lumot yo'q.
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

_HR = f"""
INSERT INTO mart.agg_hr_month (build_id, branch_id, month_id, category, headcount_plan,
                               headcount_fact, hired, fired, overtime_hours)
WITH {_MONTHS},
last AS (
  SELECT h.branch_id, h.pos_id, m.month_id, max(h.date_id) AS snap_id
  FROM dwh.hr_effective h JOIN months m ON h.date_id BETWEEN m.first_id AND m.end_id
  GROUP BY h.branch_id, h.pos_id, m.month_id),
snap AS (
  SELECT l.branch_id, l.month_id, p.category, sum(h.headcount_plan) AS plan,
         sum(h.headcount_fact) AS fact
  FROM last l
  JOIN dwh.hr_effective h ON h.branch_id = l.branch_id AND h.pos_id = l.pos_id
                    AND h.date_id = l.snap_id
  JOIN dwh.dim_position p ON p.pos_id = l.pos_id
  GROUP BY l.branch_id, l.month_id, p.category),
flow AS (
  SELECT h.branch_id, m.month_id, p.category, sum(h.hired) AS hired, sum(h.fired) AS fired,
         sum(h.overtime_hours) AS ot
  FROM dwh.hr_effective h
  JOIN months m ON h.date_id BETWEEN m.first_id AND m.end_id
  JOIN dwh.dim_position p ON p.pos_id = h.pos_id
  GROUP BY h.branch_id, m.month_id, p.category),
j AS (
  SELECT s.branch_id, s.month_id, s.category, s.plan, s.fact, f.hired, f.fired, f.ot
  FROM snap s
  JOIN flow f ON f.branch_id = s.branch_id AND f.month_id = s.month_id
             AND f.category = s.category)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, j.category, sum(j.plan), sum(j.fact),
       sum(j.hired), sum(j.fired), sum(j.ot)
FROM j
GROUP BY GROUPING SETS ((j.branch_id, j.month_id, j.category), (j.month_id, j.category))
"""

HR_MONTH = register(Aggregate("agg_hr_month", (_HR,)))
