"""Davr filtri variantlari (TZ 6 «Фильтры»): yil boshidan, choraklar, oylar — joriy yil."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.errors import ValidationFailed
from app.dwh.dates import month_end

MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
          "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
QUARTERS = ("I", "II", "III", "IV")


@dataclass(frozen=True, slots=True)
class Period:
    code: str
    kind: str  # ytd | quarter | month
    label: str
    date_from: date
    date_to: date


def build_periods(today: date) -> list[Period]:
    year, month = today.year, today.month
    if month == 1:
        ytd_label = f"{MONTHS[0]} {year}"
    else:
        ytd_label = f"{MONTHS[0]} – {MONTHS[month - 1].lower()} {year}"
    out = [Period("ytd", "ytd", ytd_label, date(year, 1, 1), today)]
    for q in range(1, (month - 1) // 3 + 2):
        start = date(year, 3 * q - 2, 1)
        end = min(month_end(date(year, 3 * q, 1)), today)
        out.append(Period(f"q{q}", "quarter", f"{QUARTERS[q - 1]} квартал {year}", start, end))
    for m in range(1, month + 1):
        start = date(year, m, 1)
        out.append(Period(f"m{m:02d}", "month", f"{MONTHS[m - 1]} {year}", start,
                          min(month_end(start), today)))
    return out


def resolve_period(code: str, today: date) -> Period:
    """Davr kodini sanalarga aylantiradi; noma'lum kod — 422. Kesh `filters`iga sanalar yoziladi."""
    for p in build_periods(today):
        if p.code == code:
            return p
    raise ValidationFailed(field="per")
