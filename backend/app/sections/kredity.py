"""«Кредиты» (TZ 5): Сводка, Реестр кредитов, График платежей.

Zanjir: router → queries.loans (pub view'lar) → Cache.respond (Redis + ETag).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.finmodel.queries import dscr_for_year
from app.sections.deps import SQ, SectionQuery
from app.sections.loan_schemas import (
    KredityGrafikOut,
    KredityReestrOut,
    KreditySvodOut,
    kpis_out,
    loan_row_out,
    named_out,
    payment_out,
    years_out,
)
from app.sections.queries import loans
from app.sections.schemas import period_out

router = APIRouter(prefix="/kredity", tags=["kredity"],
                   dependencies=[Depends(require_perm(section_perm(Section.KREDITY)))])
SVOD_UPCOMING = 5  # prototip: «Пять следующих платежей»
GRAFIK_UPCOMING = 12  # TZ 5: «двенадцать ближайших платежей»


def _dscr(db: Session, q: SectionQuery, year: int) -> float | None:
    """S5: DSCR финмоделдан (bazaviy ssenariy, hisobot yili), faqat butun kompaniya uchun."""
    return None if q.br is not None else dscr_for_year(db, year)


def build_svod(db: Session, q: SectionQuery) -> KreditySvodOut:
    period = q.period()
    r = loans.load_report(db, q.sel(), period)
    return KreditySvodOut(
        period=period_out(period), has_loans=r.has_loans,
        kpis=kpis_out(r, _dscr(db, q, r.as_of.year)),
        schedule=years_out(r), currencies=named_out(r.by_currency()),
        upcoming=[payment_out(p) for p in r.upcoming[:SVOD_UPCOMING]])


def build_reestr(db: Session, q: SectionQuery) -> KredityReestrOut:
    period = q.period()
    r = loans.load_report(db, q.sel(), period)
    return KredityReestrOut(
        period=period_out(period), has_loans=r.has_loans,
        kpis=kpis_out(r, _dscr(db, q, r.as_of.year)),
        loans=[loan_row_out(s, r.as_of) for s in r.loans],
        creditors=named_out(r.by_creditor()), currencies=named_out(r.by_currency()))


def build_grafik(db: Session, q: SectionQuery) -> KredityGrafikOut:
    period = q.period()
    r = loans.load_report(db, q.sel(), period)
    return KredityGrafikOut(
        period=period_out(period), has_loans=r.has_loans, schedule=years_out(r),
        upcoming=[payment_out(p) for p in r.upcoming[:GRAFIK_UPCOMING]])


@router.get("/svod", response_model=KreditySvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kredity.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/reestr", response_model=KredityReestrOut)
def reestr(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kredity.reestr", q.cache_filters, lambda: build_reestr(db, q))


@router.get("/grafik", response_model=KredityGrafikOut)
def grafik(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kredity.grafik", q.cache_filters, lambda: build_grafik(db, q))
