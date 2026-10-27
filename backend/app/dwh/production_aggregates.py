"""S3 ishlab chiqarish agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Stansiya = dim_branch.kind ∈ (ges, cascade): har stansiya × oy uchun qator (ishlab chiqarish
bo'lmasa ham) — КИУМ maxraji (quvvat × soat) davrning barcha oylarini qamraydi. Quvvat — oy
snapshot sanasida (end_id: oy oxiri yoki as_of) amalda bo'lgan dim_branch_version (SCD-2,
valid_to inklyuziv). Reja oylik (1-kun): ochiq oyda plan = plan_full × o'tgan kunlar / oy kunlari.
generation_cmp — oyning 1..cmp_day kunlari (o'tgan yil bilan bir xil kunlar, TZ 4).
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

_GENERATION = f"""
INSERT INTO mart.agg_generation_month (build_id, branch_id, month_id, days_in_period,
                                       days_in_month, stations, capacity_mw, capacity_hours,
                                       generation, generation_cmp, own_needs, plan, plan_full)
WITH {_MONTHS},
full_days AS (
  SELECT d.month_id, count(*)::smallint AS n FROM dwh.dim_date d
  WHERE d.month_id IN (SELECT month_id FROM months) GROUP BY d.month_id),
facts AS (
  SELECT g.branch_id, d.month_id, sum(g.generation) AS gen,
         coalesce(sum(g.generation) FILTER (WHERE d.day <= :cmp_day), 0) AS gen_cmp,
         sum(g.own_needs) AS own, coalesce(sum(g.plan), 0) AS plan_full
  FROM dwh.fact_generation g
  JOIN dwh.dim_date d ON d.date_id = g.date_id
  JOIN months m ON m.month_id = d.month_id
  WHERE g.date_id BETWEEN :from_id AND :as_of_id
  GROUP BY g.branch_id, d.month_id),
cap AS (
  SELECT b.branch_id, m.month_id, v.capacity_mw
  FROM dwh.dim_branch b
  CROSS JOIN months m
  JOIN dwh.dim_date sd ON sd.date_id = m.end_id
  LEFT JOIN dwh.dim_branch_version v ON v.branch_id = b.branch_id
       AND v.valid_from <= sd.date AND (v.valid_to IS NULL OR v.valid_to >= sd.date)
  WHERE b.kind IN ('ges', 'cascade')),
j AS (
  SELECT coalesce(c.branch_id, f.branch_id) AS branch_id,
         coalesce(c.month_id, f.month_id) AS month_id, c.capacity_mw,
         coalesce(f.gen, 0) AS gen, coalesce(f.gen_cmp, 0) AS gen_cmp,
         coalesce(f.own, 0) AS own, coalesce(f.plan_full, 0) AS plan_full
  FROM cap c FULL JOIN facts f ON f.branch_id = c.branch_id AND f.month_id = c.month_id)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, max(m.days), max(fd.n),
       count(j.capacity_mw), sum(j.capacity_mw),
       coalesce(sum(j.capacity_mw * m.days * 24), 0), sum(j.gen), sum(j.gen_cmp), sum(j.own),
       round(sum(j.plan_full) * max(m.days) / max(fd.n), 3), sum(j.plan_full)
FROM j
JOIN months m ON m.month_id = j.month_id
JOIN full_days fd ON fd.month_id = j.month_id
GROUP BY GROUPING SETS ((j.branch_id, j.month_id), (j.month_id))
"""

_ENERGY_SALES = f"""
INSERT INTO mart.agg_energy_sales_month (build_id, branch_id, month_id, accrued, paid, volume)
WITH {_MONTHS}
SELECT :build_id, coalesce(s.branch_id, 0), d.month_id, sum(s.accrued), sum(s.paid),
       sum(s.volume)
FROM dwh.fact_energy_sales s
JOIN dwh.dim_date d ON d.date_id = s.date_id
JOIN months m ON m.month_id = d.month_id
WHERE s.date_id BETWEEN :from_id AND :as_of_id
GROUP BY GROUPING SETS ((s.branch_id, d.month_id), (d.month_id))
"""

GENERATION_MONTH = register(Aggregate("agg_generation_month", (_GENERATION,)))
ENERGY_SALES_MONTH = register(Aggregate("agg_energy_sales_month", (_ENERGY_SALES,)))
