"""Kreditlar (TZ 4 «Кредиты») — faqat pub.agg_loan_month va pub.agg_loan_schedule dan.

Hisobot sanasi D = davr oxiri (ochiq davrda — bugun). Valyutadagi summalar D sanasi kursida
(snapshot'dagi fx_rate) so'mga o'giriladi; kursi yo'q kreditlar yig'indilarga kirmaydi va
`missing_fx` da qaytadi (S2 spec 4). Kreditlar soni kichik — yig'indilar Python'da.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id
from app.sections.period import ReportPeriod
from app.sections.scope import BranchSel

UZS = "UZS"
HORIZON_YEARS = 10  # TZ 5: «График погашения 2026–2035»


def _opt(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def _convert(amount: Decimal, fx_rate: Decimal | None) -> float | None:
    return None if fx_rate is None else round(float(amount * fx_rate), 2)


@dataclass(frozen=True, slots=True)
class LoanSnap:
    loan_id: int
    branch_id: int
    branch_name: str
    loan_code: str
    creditor: str
    project: str
    currency: str
    rate: float
    grace_until: date | None
    maturity: date
    fx_rate: float | None
    original_cur: float
    outstanding_cur: float
    outstanding: float | None

    @property
    def repaid_share(self) -> float | None:
        """Доля погашения = 1 − qoldiq / boshlang'ich summa (kredit valyutasida)."""
        if self.original_cur <= 0:
            return None
        return round(1 - self.outstanding_cur / self.original_cur, 6)

    def in_grace(self, day: date) -> bool:
        return self.grace_until is not None and self.grace_until > day


@dataclass(frozen=True, slots=True)
class LoanPayment:
    day: date
    loan_id: int
    creditor: str
    project: str
    branch_name: str
    principal: float | None
    interest: float | None

    @property
    def total(self) -> float | None:
        if self.principal is None or self.interest is None:
            return None
        return round(self.principal + self.interest, 2)


@dataclass(frozen=True, slots=True)
class YearLoad:
    year: int
    principal: float
    interest: float

    @property
    def total(self) -> float:
        return round(self.principal + self.interest, 2)


@dataclass(frozen=True, slots=True)
class LoanReport:
    as_of: date
    loans: list[LoanSnap]
    payments: list[LoanPayment]
    portfolio: float | None
    rate: float | None
    fx_share: float | None
    fx_amount: float
    service: float
    paid: float
    missing_fx: list[str]
    years: list[YearLoad]

    @property
    def has_loans(self) -> bool:
        return bool(self.loans)

    @property
    def paid_share(self) -> float | None:
        return None if self.service <= 0 else self.paid / self.service

    @property
    def upcoming(self) -> list[LoanPayment]:
        return [p for p in self.payments if p.day > self.as_of]

    @property
    def next_payment(self) -> LoanPayment | None:
        upcoming = self.upcoming
        return upcoming[0] if upcoming else None

    @property
    def peak(self) -> YearLoad | None:
        best = max(self.years, key=lambda y: y.total, default=None)
        return best if best is not None and best.total > 0 else None

    def _group(self, key: str) -> list[tuple[str, float]]:
        totals: dict[str, float] = {}
        for loan in self.loans:
            if loan.outstanding is not None:
                name = loan.currency if key == "currency" else loan.creditor
                totals[name] = round(totals.get(name, 0.0) + loan.outstanding, 2)
        return sorted(totals.items(), key=lambda item: (-item[1], item[0]))

    def by_currency(self) -> list[tuple[str, float]]:
        return self._group("currency")

    def by_creditor(self) -> list[tuple[str, float]]:
        return self._group("creditor")


def snapshots(db: Session, sel: BranchSel, month: int) -> list[LoanSnap]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.loan_id, a.branch_id, b.name AS branch_name, a.loan_code, a.creditor, "
        "a.project, a.currency, a.rate, a.grace_until, a.maturity, a.fx_rate, a.original_cur, "
        "a.outstanding_cur, a.outstanding "
        "FROM pub.agg_loan_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE a.month_id = :m AND {where} "
        "ORDER BY a.outstanding DESC NULLS LAST, a.loan_id"), {**params, "m": month}).all()
    return [LoanSnap(int(r.loan_id), int(r.branch_id), r.branch_name, r.loan_code, r.creditor,
                     r.project, str(r.currency).strip(), float(r.rate), r.grace_until,
                     r.maturity, _opt(r.fx_rate), float(r.original_cur),
                     float(r.outstanding_cur), _opt(r.outstanding)) for r in rows]


def schedule(db: Session, sel: BranchSel, month: int) -> list[LoanPayment]:
    """Grafik qatorlari shu oy snapshot'idagi kurs bilan (snapshot'i yo'q kreditlar — yo'q)."""
    where, params = sel.rows("s.branch_id")
    rows = db.execute(text(
        "SELECT s.date_id, s.loan_id, a.creditor, a.project, b.name AS branch_name, "
        "s.principal_cur, s.interest_cur, a.fx_rate "
        "FROM pub.agg_loan_schedule s "
        "JOIN pub.agg_loan_month a ON a.loan_id = s.loan_id AND a.branch_id = s.branch_id "
        "AND a.month_id = :m "
        "JOIN pub.branches b ON b.branch_id = s.branch_id "
        f"WHERE {where} ORDER BY s.date_id, s.loan_id"), {**params, "m": month}).all()
    return [LoanPayment(from_date_id(int(r.date_id)), int(r.loan_id), r.creditor, r.project,
                        r.branch_name, _convert(r.principal_cur, r.fx_rate),
                        _convert(r.interest_cur, r.fx_rate)) for r in rows]


def compute_report(snaps: list[LoanSnap], payments: list[LoanPayment], as_of: date) -> LoanReport:
    known = [(s, s.outstanding) for s in snaps if s.outstanding is not None]
    total = round(sum(value for _, value in known), 2)
    fx_amount = round(sum(value for s, value in known if s.currency != UZS), 2)
    weighted = sum(value * s.rate for s, value in known)
    year = as_of.year
    ordered = sorted(payments, key=lambda p: (p.day, -(p.total or 0.0), p.loan_id))
    in_year = [(p, t) for p in ordered if p.day.year == year for t in (p.total,) if t is not None]
    years: list[YearLoad] = []
    for y in range(year, year + HORIZON_YEARS):
        rows = [p for p in ordered if p.day.year == y]
        years.append(YearLoad(
            y,
            round(sum(v for v in (p.principal for p in rows) if v is not None), 2),
            round(sum(v for v in (p.interest for p in rows) if v is not None), 2)))
    return LoanReport(
        as_of=as_of,
        loans=list(snaps),
        payments=ordered,
        portfolio=total if known else None,
        rate=weighted / total if total > 0 else None,
        fx_share=fx_amount / total if total > 0 else None,
        fx_amount=fx_amount,
        service=round(sum(t for _, t in in_year), 2),
        paid=round(sum(t for p, t in in_year if p.day <= as_of), 2),
        missing_fx=sorted({s.currency for s in snaps if s.fx_rate is None}),
        years=years,
    )


def load_report(db: Session, sel: BranchSel, period: ReportPeriod) -> LoanReport:
    month = period.last_month
    return compute_report(snapshots(db, sel, month), schedule(db, sel, month), period.date_to)
