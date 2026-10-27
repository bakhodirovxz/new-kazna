"""S3 ombor agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Oy snapshot'i: filial × oy ichidagi eng oxirgi fact_stock sanasi va faqat shu sanadagi qatorlar
(oy davomidagi oldingi snapshot'lar tashlanadi — pozitsiya yo'qolgan bo'lsa, qayta sanalmaydi).
Bir xil pozitsiya (nomenklatura × ombor) bir nechta manbadan kelsa — yig'indi.
Yosh = snapshot sanasi − oxirgi harakat sanasi; ma'lum emas → age_unknown (TZ 4 «возраст запасов»).
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

IDLE_DAYS = 180  # TZ 4: неликвиды — без движения более 180 дней

_POSITIONS_CTE = f"""{_MONTHS},
last_snap AS (
  SELECT s.branch_id, m.month_id, max(s.date_id) AS snap_id
  FROM dwh.fact_stock s JOIN months m ON s.date_id BETWEEN m.first_id AND m.end_id
  GROUP BY s.branch_id, m.month_id),
snap AS (
  SELECT s.branch_id, l.month_id, s.nom_id, s.warehouse, l.snap_id, sum(s.qty) AS qty,
         sum(s.value) AS value, max(s.min_qty) AS min_qty,
         max(s.last_move_date_id) AS last_move_date_id
  FROM dwh.fact_stock s
  JOIN last_snap l ON l.branch_id = s.branch_id AND s.date_id = l.snap_id
  GROUP BY s.branch_id, l.month_id, s.nom_id, s.warehouse, l.snap_id),
pos AS (
  SELECT sn.branch_id, sn.month_id, sn.nom_id, sn.warehouse, sn.snap_id, sn.qty, sn.value,
         sn.min_qty, sn.last_move_date_id, n.code AS nom_code, n.name, n.category, n.unit,
         (sd.date - lm.date) AS age_days
  FROM snap sn
  JOIN dwh.dim_nomenclature n ON n.nom_id = sn.nom_id
  JOIN dwh.dim_date sd ON sd.date_id = sn.snap_id
  LEFT JOIN dwh.dim_date lm ON lm.date_id = sn.last_move_date_id)"""

_STOCK_MONTH = f"""
INSERT INTO mart.agg_stock_month (build_id, branch_id, month_id, category, snap_date_id,
                                  positions, value, below_min, min_known, idle_value, age_le90,
                                  age_91_180, age_181_365, age_gt365, age_unknown, inflow,
                                  outflow)
WITH {_POSITIONS_CTE},
st AS (
  SELECT branch_id, month_id, category, max(snap_id) AS snap_id,
         count(*) FILTER (WHERE qty > 0 OR value > 0) AS positions, sum(value) AS value,
         count(*) FILTER (WHERE min_qty IS NOT NULL AND qty < min_qty) AS below_min,
         count(*) FILTER (WHERE min_qty IS NOT NULL) AS min_known,
         coalesce(sum(value) FILTER (WHERE age_days > {IDLE_DAYS}), 0) AS idle_value,
         coalesce(sum(value) FILTER (WHERE age_days <= 90), 0) AS a1,
         coalesce(sum(value) FILTER (WHERE age_days BETWEEN 91 AND 180), 0) AS a2,
         coalesce(sum(value) FILTER (WHERE age_days BETWEEN 181 AND 365), 0) AS a3,
         coalesce(sum(value) FILTER (WHERE age_days > 365), 0) AS a4,
         coalesce(sum(value) FILTER (WHERE age_days IS NULL), 0) AS a0
  FROM pos GROUP BY branch_id, month_id, category),
mv AS (
  SELECT f.branch_id, d.month_id, n.category,
         coalesce(sum(f.value) FILTER (WHERE f.direction = 'in'), 0) AS inflow,
         coalesce(sum(f.value) FILTER (WHERE f.direction = 'out'), 0) AS outflow
  FROM dwh.fact_stock_move f
  JOIN dwh.dim_date d ON d.date_id = f.date_id
  JOIN months m ON m.month_id = d.month_id
  JOIN dwh.dim_nomenclature n ON n.nom_id = f.nom_id
  WHERE f.date_id BETWEEN :from_id AND :as_of_id
  GROUP BY f.branch_id, d.month_id, n.category),
j AS (
  SELECT coalesce(st.branch_id, mv.branch_id) AS branch_id,
         coalesce(st.month_id, mv.month_id) AS month_id,
         coalesce(st.category, mv.category) AS category, st.snap_id,
         coalesce(st.positions, 0) AS positions, coalesce(st.value, 0) AS value,
         coalesce(st.below_min, 0) AS below_min, coalesce(st.min_known, 0) AS min_known,
         coalesce(st.idle_value, 0) AS idle_value, coalesce(st.a1, 0) AS a1,
         coalesce(st.a2, 0) AS a2, coalesce(st.a3, 0) AS a3, coalesce(st.a4, 0) AS a4,
         coalesce(st.a0, 0) AS a0, coalesce(mv.inflow, 0) AS inflow,
         coalesce(mv.outflow, 0) AS outflow
  FROM st FULL JOIN mv ON mv.branch_id = st.branch_id AND mv.month_id = st.month_id
                      AND mv.category = st.category)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, j.category, max(j.snap_id),
       sum(j.positions), sum(j.value), sum(j.below_min), sum(j.min_known), sum(j.idle_value),
       sum(j.a1), sum(j.a2), sum(j.a3), sum(j.a4), sum(j.a0), sum(j.inflow), sum(j.outflow)
FROM j
GROUP BY GROUPING SETS ((j.branch_id, j.month_id, j.category), (j.month_id, j.category))
"""

_STOCK_POSITIONS = f"""
INSERT INTO mart.agg_stock_positions (build_id, branch_id, month_id, nom_id, warehouse,
                                      snap_date_id, nom_code, name, category, unit, qty,
                                      min_qty, value, last_move_date_id, age_days, below_min,
                                      idle)
WITH {_POSITIONS_CTE}
SELECT :build_id, branch_id, month_id, nom_id, warehouse, snap_id, nom_code, name, category,
       unit, qty, min_qty, value, last_move_date_id, age_days,
       coalesce(min_qty IS NOT NULL AND qty < min_qty, false),
       coalesce(age_days > {IDLE_DAYS}, false)
FROM pos
WHERE (min_qty IS NOT NULL AND qty < min_qty) OR age_days > {IDLE_DAYS}
"""

STOCK_MONTH = register(Aggregate("agg_stock_month", (_STOCK_MONTH,)))
STOCK_POSITIONS = register(Aggregate("agg_stock_positions", (_STOCK_POSITIONS,)))
