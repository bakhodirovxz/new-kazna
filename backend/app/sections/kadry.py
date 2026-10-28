"""«Кадры» (TZ 5): Сводка, Численность, Оплата труда, Движение кадров.

ФОТ statyalari — S1 `kazna.calendar_kinds.salary` (bir joyda sozlanadi). Sozlama o'zgarsa kesh
keyingi ma'lumot versiyasida yangilanadi (S1 kalendari bilan bir xil xulq).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core import sysconfig
from app.core.cache import Cache
from app.core.db import DB
from app.dwh.reference import current_setting
from app.sections.deps import SQ, SectionQuery
from app.sections.kadry_schemas import (
    HrCategoryOut,
    HrKpisOut,
    HrMonthOut,
    KadryChislennostOut,
    KadryDvizhenieOut,
    KadryFotOut,
    KadrySvodOut,
    KadryYavkaOut,
    hr_branch_out,
    hr_category_out,
    hr_kpis_out,
    hr_month_out,
    yavka_out,
)
from app.sections.proizvodstvo import Now
from app.sections.queries import attendance, hr
from app.sections.schemas import period_out

router = APIRouter(prefix="/kadry", tags=["kadry"],
                   dependencies=[Depends(require_perm(section_perm(Section.KADRY)))])


def salary_codes(db: Session) -> list[str]:
    kinds = current_setting(db.connection(), "kazna.calendar_kinds")
    return [str(code) for code in kinds.get("salary", [])]


def min_group() -> int:
    """k-anonimlik chegarasi: guruh < kadry.min_group bo'lsa ФОТ/o'rtacha yashiriladi."""
    return int(sysconfig.value("kadry.min_group"))


def _months(db: Session, q: SectionQuery, codes: list[str]) -> list[HrMonthOut]:
    return [hr_month_out(m) for m in hr.monthly(db, q.sel(), q.today, codes, min_group())]


def _categories(db: Session, q: SectionQuery) -> list[HrCategoryOut]:
    return [hr_category_out(c) for c in hr.categories(db, q.sel(), q.period(), min_group())]


def _kpis(db: Session, q: SectionQuery, codes: list[str]) -> HrKpisOut:
    return hr_kpis_out(hr.totals(db, q.sel(), q.period(), codes, min_group()))


def _branches(db: Session, q: SectionQuery, codes: list[str]) -> list[hr.HrBranch]:
    return hr.by_branch(db, q.sel(), q.period(), codes, min_group())


def build_svod(db: Session, q: SectionQuery) -> KadrySvodOut:
    period, codes = q.period(), salary_codes(db)
    return KadrySvodOut(
        period=period_out(period), kpis=_kpis(db, q, codes),
        months=_months(db, q, codes), categories=_categories(db, q),
        branches=[hr_branch_out(b) for b in _branches(db, q, codes)])


def build_chislennost(db: Session, q: SectionQuery) -> KadryChislennostOut:
    period, codes = q.period(), salary_codes(db)
    return KadryChislennostOut(
        period=period_out(period), kpis=_kpis(db, q, codes),
        branches=[hr_branch_out(b) for b in _branches(db, q, codes)],
        categories=_categories(db, q))


def build_fot(db: Session, q: SectionQuery) -> KadryFotOut:
    period, codes = q.period(), salary_codes(db)
    # yashirilgan filiallar tartibi ФОТ miqdorini ochmasligi uchun ularning kaliti 0
    rows = sorted(_branches(db, q, codes),
                  key=lambda b: (0.0 if b.hidden else -b.payroll, b.name))
    return KadryFotOut(
        period=period_out(period), kpis=_kpis(db, q, codes),
        months=_months(db, q, codes), branches=[hr_branch_out(b) for b in rows])


def build_dvizhenie(db: Session, q: SectionQuery) -> KadryDvizhenieOut:
    period, codes = q.period(), salary_codes(db)
    rows = sorted(_branches(db, q, codes), key=lambda b: (-(b.turnover or 0.0), b.name))
    return KadryDvizhenieOut(
        period=period_out(period), kpis=_kpis(db, q, codes),
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


@router.get("/yavka", response_model=KadryYavkaOut)
def yavka(db: DB, q: SQ, now: Now) -> KadryYavkaOut:
    """Davomat (HR API): worker 10 daqiqada yangilaydi - kesh yo'q, har so'rovda o'qiladi."""
    stale = int(current_setting(db.connection(), "hr.attendance_stale_minutes"))
    return yavka_out(attendance.load(db, q.sel(), today=q.today, now=now, stale_minutes=stale))
