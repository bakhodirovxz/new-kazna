"""S4 xarid agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Lotlar reyestri — barcha KPI'lar manbai (bitta snapshot): «в работе» kunlari build sanasiga
(as_of − e'lon sanasi), normativ — build vaqtidagi `zakupki.method_norms` sozlamasi (panel >
standart). Kechikish TZ 4: kunlar > normativ + 10. Normativ o'zgarsa —
keyingi build'dan (eski build'lar reproduksiya qilinadigan bo'lib qoladi).
"""

from __future__ import annotations

from app.dwh.aggregates import Aggregate, register
from app.etl.zakupki.codes import IN_WORK, LATE_MARGIN_DAYS, PLAN_DOC

# Normativlar `:method_norms` (jsonb) sifatida build_all'dan keladi (sysconfig: panel > standart).
# IN_WORK/PLAN_DOC — kod ichidagi konstantalar, SQL literal sifatida xavfsiz.
_IN_WORK = ", ".join(f"'{s}'" for s in IN_WORK)

_LOTS = f"""
INSERT INTO mart.agg_procurement_lots (build_id, branch_id, month_id, lot_src, date_id, lot_no,
                                       method, status, start_price, contract_price, days,
                                       norm_days, overdue, subject, supplier)
WITH norms AS (
  SELECT CAST(:method_norms AS jsonb) AS v),
lots AS (
  SELECT p.*, d.month_id,
         CASE WHEN p.status IN ({_IN_WORK}) THEN CAST(:as_of AS date) - d.date
              ELSE p.procedure_days END AS days,
         CAST(nr.v ->> p.method AS integer) AS norm_days
  FROM dwh.fact_procurement p
  JOIN dwh.dim_date d ON d.date_id = p.date_id
  CROSS JOIN norms nr
  WHERE p.doc_type <> '{PLAN_DOC}' AND p.date_id BETWEEN :from_id AND :as_of_id)
SELECT :build_id, l.branch_id, l.month_id,
       l.src_system || ':' || l.doc_type || ':' || l.src_id, l.date_id, l.lot_no, l.method,
       l.status, l.start_price, l.contract_price, l.days, l.norm_days,
       coalesce(l.status IN ({_IN_WORK}) AND l.days > l.norm_days + {LATE_MARGIN_DAYS}, false),
       coalesce(n.category, '—'), c.name
FROM lots l
LEFT JOIN dwh.dim_nomenclature n ON n.nom_id = l.nom_id
LEFT JOIN dwh.dim_counterparty c ON c.cp_id = l.cp_id
"""

_PLAN = f"""
INSERT INTO mart.agg_procurement_plan (build_id, branch_id, month_id, plan)
SELECT :build_id, coalesce(p.branch_id, 0), d.year * 100 + 1, sum(p.start_price)
FROM dwh.fact_procurement p
JOIN dwh.dim_date d ON d.date_id = p.date_id
WHERE p.doc_type = '{PLAN_DOC}' AND p.date_id BETWEEN :from_id AND :as_of_id
GROUP BY GROUPING SETS ((p.branch_id, d.year), (d.year))
"""

PROCUREMENT_LOTS = register(Aggregate("agg_procurement_lots", (_LOTS,)))
PROCUREMENT_PLAN = register(Aggregate("agg_procurement_plan", (_PLAN,)))
