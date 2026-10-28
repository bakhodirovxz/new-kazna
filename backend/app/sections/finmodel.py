"""«Финмодель» (TZ 5): Сводка, Доходы и расходы, Инвестиции и долг, Сценарии — bitta endpoint.

Model kompaniya darajasida (branch_id = 0) — 28 qator; KPI, ssenariylar va sezgirlik shu
qatorlardan yig'iladi (og'ir hisob so'rovda yo'q). Kesh kaliti — ssenariy va допущения vaqti
(допущения o'zgarsa «изменены после расчёта» belgisi darhol ko'rinadi).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.dwh.reference import SCENARIOS
from app.finmodel.queries import assumptions_updated_at, load_model
from app.finmodel.summary import sensitivity, summarize
from app.sections.deps import SQ, SectionQuery
from app.sections.finmodel_schemas import (
    FinBaseOut,
    FinmodelOut,
    sensitivity_out,
    summary_out,
    year_out,
)

router = APIRouter(prefix="/finmodel", tags=["finmodel"],
                   dependencies=[Depends(require_perm(section_perm(Section.FINMODEL)))])
SCEN_PATTERN = r"^(base|water|tariff|fx)$"


def build_model(db: Session, q: SectionQuery, scen: str) -> FinmodelOut:
    model = load_model(db)
    company_wide = q.br is not None
    if model is None or scen not in model.years:
        return FinmodelOut(has_model=False, scenario=scen, company_wide=company_wide, base=None,
                           years=[], summary=None, scenarios=[], sensitivity=[])
    b = model.base
    summaries = {s: summarize(s, model.years[s], base_capacity=b.capacity_mw,
                              covenant=b.covenant) for s in SCENARIOS if s in model.years}
    current = assumptions_updated_at(db)
    stale = current is not None and (b.assumptions_at is None or current > b.assumptions_at)
    base_years = model.years.get("base", model.years[scen])
    base = FinBaseOut(
        as_of=b.as_of, capacity_mw=b.capacity_mw, opex_base=b.opex_base,
        opex_months=b.opex_months, opening_cash=b.opening_cash, missing_fx=b.missing_fx,
        aip_missing_years=[y.year for y in base_years if y.capex_plan == 0],
        assumptions_at=b.assumptions_at, stale_assumptions=stale, covenant=b.covenant)
    return FinmodelOut(
        has_model=True, scenario=scen, company_wide=company_wide, base=base,
        years=[year_out(y) for y in model.years[scen]], summary=summary_out(summaries[scen]),
        scenarios=[summary_out(summaries[s]) for s in SCENARIOS if s in summaries],
        sensitivity=[sensitivity_out(x) for x in sensitivity(summaries)])


@router.get("/model", response_model=FinmodelOut)
def model(cache: Cache, db: DB, q: SQ,
          scen: Annotated[str, Query(pattern=SCEN_PATTERN)] = "base") -> Response:
    stamp = assumptions_updated_at(db)
    filters = {**q.cache_filters, "scen": scen,
               "assumptions_at": None if stamp is None else stamp.isoformat()}
    return cache.respond("finmodel.model", filters, lambda: build_model(db, q, scen))
