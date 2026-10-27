"""S4 АИП agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Oylar: date_from … joriy yil dekabri (reja kelajak oylar uchun ham kerak — «Программа года»).
Har obyekt birinchi qatori bor oydan boshlab har oy qator oladi (qatorsiz oylar — nol): КС-2
foizi oxirgi ma'lum qiymat bilan, avans — oxirgi mavjud qator qiymati bilan oldinga to'ldiriladi
(faqat as_of oyigacha; keyingi oylarda NULL). «aip_opening» (tarixdan oldingi to'plangan
moliyalashtirish) oylik faktga emas, `opening` ga tushadi — «освоено ранее» (TZ 4).
Obyekt atributlari denormalizatsiya qilinadi — pub'da obyektlar ro'yxati alohida ochilmaydi.
"""

from __future__ import annotations

from app.dwh.aggregates import Aggregate, register

OPEN_DOC = "aip_opening"
_AS_MONTH = "CAST(:as_of_id AS integer) / 100"

_INVESTMENT = f"""
INSERT INTO mart.agg_investment_month (build_id, branch_id, month_id, object_id, object_code,
                                       name, program_code, work_type, source_name,
                                       commissioning_year, total_cost, plan, fact, opening,
                                       physical_pct, advance, advance_date_id)
WITH months AS (
  SELECT month_id FROM dwh.dim_date
  WHERE date BETWEEN CAST(:date_from AS date)
                 AND make_date(CAST(extract(year FROM CAST(:as_of AS date)) AS integer), 12, 31)
  GROUP BY month_id),
f AS (
  SELECT i.branch_id, i.object_id, d.month_id, sum(i.plan) AS plan,
         coalesce(sum(i.fact) FILTER (WHERE i.doc_type <> '{OPEN_DOC}'), 0) AS fact,
         coalesce(sum(i.fact) FILTER (WHERE i.doc_type = '{OPEN_DOC}'), 0) AS opening,
         (array_agg(i.physical_pct ORDER BY i.date_id DESC)
            FILTER (WHERE i.physical_pct IS NOT NULL))[1] AS phys,
         sum(i.advance) AS adv,
         min(i.advance_date_id) FILTER (WHERE i.advance > 0) AS adv_date
  FROM dwh.fact_investment i
  JOIN dwh.dim_date d ON d.date_id = i.date_id
  JOIN months m ON m.month_id = d.month_id
  GROUP BY i.branch_id, i.object_id, d.month_id),
grid AS (
  SELECT o.branch_id, o.object_id, m.month_id
  FROM (SELECT branch_id, object_id, min(month_id) AS first_m FROM f
        GROUP BY branch_id, object_id) o
  JOIN months m ON m.month_id >= o.first_m),
j AS (
  SELECT g.branch_id, g.object_id, g.month_id, coalesce(f.plan, 0) AS plan,
         coalesce(f.fact, 0) AS fact, coalesce(f.opening, 0) AS opening, f.phys, f.adv,
         f.adv_date,
         count(f.phys) OVER w AS phys_grp,
         count(f.month_id) OVER w AS row_grp
  FROM grid g
  LEFT JOIN f ON f.branch_id = g.branch_id AND f.object_id = g.object_id
             AND f.month_id = g.month_id
  WINDOW w AS (PARTITION BY g.branch_id, g.object_id ORDER BY g.month_id)),
k AS (
  SELECT j.*,
         first_value(j.phys) OVER (PARTITION BY j.branch_id, j.object_id, j.phys_grp
                                   ORDER BY j.month_id) AS phys_ff,
         first_value(j.adv) OVER (PARTITION BY j.branch_id, j.object_id, j.row_grp
                                  ORDER BY j.month_id) AS adv_ff,
         first_value(j.adv_date) OVER (PARTITION BY j.branch_id, j.object_id, j.row_grp
                                       ORDER BY j.month_id) AS adv_date_ff
  FROM j)
SELECT :build_id, k.branch_id, k.month_id, k.object_id, o.code, o.name, o.program_code,
       o.work_type, coalesce(s.name, '—'), o.commissioning_year, o.total_cost, k.plan, k.fact,
       k.opening,
       CASE WHEN k.month_id <= {_AS_MONTH} THEN k.phys_ff END,
       CASE WHEN k.month_id <= {_AS_MONTH} THEN coalesce(k.adv_ff, 0) END,
       CASE WHEN k.month_id <= {_AS_MONTH} THEN k.adv_date_ff END
FROM k
JOIN dwh.dim_object o ON o.object_id = k.object_id
LEFT JOIN dwh.dim_source s ON s.source_id = o.source_id
"""

_STAGES = f"""
INSERT INTO mart.agg_object_stages (build_id, branch_id, month_id, object_id, stage_no,
                                    stage_name, plan_date_id, fact_date_id, done, late)
SELECT :build_id, s.branch_id, {_AS_MONTH}, s.object_id, s.stage_no, max(s.stage_name),
       max(s.date_id), max(s.fact_date_id), max(s.fact_date_id) IS NOT NULL,
       coalesce(max(s.fact_date_id) > max(s.date_id), max(s.date_id) < :as_of_id)
FROM dwh.fact_object_stage s
GROUP BY s.branch_id, s.object_id, s.stage_no
"""

INVESTMENT_MONTH = register(Aggregate("agg_investment_month", (_INVESTMENT,)))
OBJECT_STAGES = register(Aggregate("agg_object_stages", (_STAGES,)))
