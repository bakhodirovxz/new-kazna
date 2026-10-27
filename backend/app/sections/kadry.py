"""«Кадры» (TZ 5): Сводка, Численность, Оплата труда, Движение кадров.

ФОТ statyalari — S1 `kazna.calendar_kinds.salary` (bir joyda sozlanadi). Sozlama o'zgarsa kesh
keyingi ma'lumot versiyasida yangilanadi (S1 kalendari bilan bir xil xulq).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.dwh.reference import current_setting
from app.sections.deps import SQ, SectionQuery
from app.sections.kadry_schemas import (
    HrCategoryOut,
    HrMonthOut,
    KadryChislennostOut,
    KadryDvizhenieOut,
    KadryFotOut,
    KadrySvodOut,
    hr_branch_out,
    hr_kpis_out,
)
from app.sections.queries import hr
from app.sections.schemas import period_out

router = APIRouter(prefix="/kadry", tags=["kadry"],
                   dependencies=[Depends(require_perm(section_perm(Section.KADRY)))])


def salary_codes(db: Session) -> list[str]:
    kinds = current_setting(db.connection(), "kazna.calendar_kinds")
    return [str(code) for code in kinds.get("salary", [])]


def _months(db: Session, q: SectionQuery, codes: list[str]) -> list[HrMonthOut]:
    return [HrMonthOut(month_id=m.month_id, payroll=m.payroll, fact=m.fact,
                       avg_salary=m.avg_salary, hired=m.hired, fired=m.fired,
                       overtime=m.overtime) for m in hr.monthly(db, q.sel(), q.today, codes)]


def _categories(db: Session, q: SectionQuery) -> list[HrCategoryOut]:
    return [HrCategoryOut(name=c.name, value=c.value)
            for c in hr.categories(db, q.sel(), q.period())]


def build_svod(db: Session, q: SectionQuery) -> KadrySvodOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    return KadrySvodOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        months=_months(db, q, codes), categories=_categories(db, q),
        branches=[hr_branch_out(b) for b in hr.by_branch(db, sel, period, codes)])


def build_chislennost(db: Session, q: SectionQuery) -> KadryChislennostOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    return KadryChislennostOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        branches=[hr_branch_out(b) for b in hr.by_branch(db, sel, period, codes)],
        categories=_categories(db, q))


def build_fot(db: Session, q: SectionQuery) -> KadryFotOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    rows = sorted(hr.by_branch(db, sel, period, codes), key=lambda b: (-b.payroll, b.name))
    return KadryFotOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        months=_months(db, q, codes), branches=[hr_branch_out(b) for b in rows])


def build_dvizhenie(db: Session, q: SectionQuery) -> KadryDvizhenieOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    rows = sorted(hr.by_branch(db, sel, period, codes),
                  key=lambda b: (-(b.turnover or 0.0), b.name))
    return KadryDvizhenieOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        months=_months(db, q, codes), branches=[hr_branch_out(b) for b in rows])


@router.get("/svod", response_model=KadrySvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/chislennost", response_model=KadryChislennostOut)
def chislennost(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.chislennost", q.cache_filters,
                         lambda: build_chislennost(db, q))


@router.get("/fot", response_model=KadryFotOut)
def fot(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.fot", q.cache_filters, lambda: build_fot(db, q))


@router.get("/dvizhenie", response_model=KadryDvizhenieOut)
def dvizhenie(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.dvizhenie", q.cache_filters, lambda: build_dvizhenie(db, q))
