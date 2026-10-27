"""«Кредиты» API javoblari (OpenAPI komponent nomlari noyob). Summalar mln so'm (D kursida);
`*_cur` — kredit valyutasida (mln birlik); None — ma'lumot yoki kurs yo'q."""

from __future__ import annotations

from datetime import date

from app.sections.queries.loans import LoanPayment, LoanReport, LoanSnap
from app.sections.schemas import ReportPeriodOut, _Out


class LoanPaymentOut(_Out):
    day: date
    loan_id: int
    creditor: str
    project: str
    branch_name: str
    principal: float | None
    interest: float | None
    total: float | None


class LoanKpisOut(_Out):
    as_of: date
    loans: int
    portfolio: float | None
    rate: float | None
    fx_share: float | None
    service: float
    paid: float
    paid_share: float | None
    next_payment: LoanPaymentOut | None
    peak_year: int | None
    peak_amount: float | None
    missing_fx: list[str]
    # DSCR = EBITDA / обслуживание долга — Финмодель (S5) ulanmaguncha None («нет данных»).
    dscr: float | None


class LoanYearOut(_Out):
    year: int
    principal: float
    interest: float


class NamedAmountOut(_Out):
    name: str
    amount: float


class LoanRowOut(_Out):
    loan_id: int
    loan_code: str
    creditor: str
    project: str
    branch_id: int
    branch_name: str
    currency: str
    rate: float
    outstanding: float | None
    outstanding_cur: float
    original_cur: float
    repaid_share: float | None
    grace_until: date | None
    in_grace: bool
    maturity: date


class KreditySvodOut(_Out):
    period: ReportPeriodOut
    has_loans: bool
    kpis: LoanKpisOut
    schedule: list[LoanYearOut]
    currencies: list[NamedAmountOut]
    upcoming: list[LoanPaymentOut]


class KredityReestrOut(_Out):
    period: ReportPeriodOut
    has_loans: bool
    kpis: LoanKpisOut
    loans: list[LoanRowOut]
    creditors: list[NamedAmountOut]
    currencies: list[NamedAmountOut]


class KredityGrafikOut(_Out):
    period: ReportPeriodOut
    has_loans: bool
    schedule: list[LoanYearOut]
    upcoming: list[LoanPaymentOut]


def payment_out(p: LoanPayment) -> LoanPaymentOut:
    return LoanPaymentOut(day=p.day, loan_id=p.loan_id, creditor=p.creditor, project=p.project,
                          branch_name=p.branch_name, principal=p.principal,
                          interest=p.interest, total=p.total)


def kpis_out(r: LoanReport) -> LoanKpisOut:
    peak = r.peak
    nxt = r.next_payment
    return LoanKpisOut(
        as_of=r.as_of, loans=len(r.loans), portfolio=r.portfolio, rate=r.rate,
        fx_share=r.fx_share, service=r.service, paid=r.paid, paid_share=r.paid_share,
        next_payment=None if nxt is None else payment_out(nxt),
        peak_year=None if peak is None else peak.year,
        peak_amount=None if peak is None else peak.total,
        missing_fx=r.missing_fx, dscr=None)


def years_out(r: LoanReport) -> list[LoanYearOut]:
    return [LoanYearOut(year=y.year, principal=y.principal, interest=y.interest)
            for y in r.years]


def named_out(items: list[tuple[str, float]]) -> list[NamedAmountOut]:
    return [NamedAmountOut(name=name, amount=amount) for name, amount in items]


def loan_row_out(s: LoanSnap, as_of: date) -> LoanRowOut:
    return LoanRowOut(
        loan_id=s.loan_id, loan_code=s.loan_code, creditor=s.creditor, project=s.project,
        branch_id=s.branch_id, branch_name=s.branch_name, currency=s.currency, rate=s.rate,
        outstanding=s.outstanding, outstanding_cur=s.outstanding_cur,
        original_cur=s.original_cur, repaid_share=s.repaid_share, grace_until=s.grace_until,
        in_grace=s.in_grace(as_of), maturity=s.maturity)
