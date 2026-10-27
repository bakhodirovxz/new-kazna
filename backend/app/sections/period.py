"""Hisobot davri (TZ 6 «Фильтры»): `per` kodi → oylar ro'yxati (`/meta/periods` kodlari)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from app.core.errors import ValidationFailed
from app.dwh.dates import add_months, month_id, month_start
from app.meta.periods import build_periods


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    code: str
    label: str
    date_from: date
    date_to: date
    today: date
    months: tuple[int, ...]

    @property
    def first_month(self) -> int:
        return self.months[0]

    @property
    def last_month(self) -> int:
        return self.months[-1]

    @property
    def open_last(self) -> bool:
        """Oxirgi oy yopilmagan (joriy) — o'tgan yil bilan shuncha kun bo'yicha solishtiriladi."""
        return self.last_month == month_id(self.today)

    @property
    def prev_months(self) -> tuple[int, ...]:
        return tuple(m - 100 for m in self.months)

    @property
    def month_equivalents(self) -> float:
        """Oylar soni; joriy oy o'tgan kunlar ulushi bilan (o'rtacha oylik расходование uchun)."""
        current = month_id(self.today)
        days = calendar.monthrange(self.today.year, self.today.month)[1]
        return sum(self.today.day / days if m == current else 1.0 for m in self.months)


def normalize_per(code: str) -> str:
    """TZ xatcho'plari `per=05` -> `m05` (kesh kaliti ham shu shaklda)."""
    return f"m{code}" if code.isdigit() and len(code) == 2 else code


def resolve_period(code: str, today: date) -> ReportPeriod:
    code = normalize_per(code)
    for period in build_periods(today):
        if period.code != code:
            continue
        months: list[int] = []
        cur = month_start(period.date_from)
        while cur <= period.date_to:
            months.append(month_id(cur))
            cur = add_months(cur, 1)
        return ReportPeriod(period.code, period.label, period.date_from, period.date_to, today,
                            tuple(months))
    raise ValidationFailed(fields=["per"])
