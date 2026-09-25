"""Sana kalitlari: date_id = YYYYMMDD, month_id = YYYYMM."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta, timezone


def date_id(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def month_id(d: date) -> int:
    return d.year * 100 + d.month


def from_date_id(value: int) -> date:
    return date(value // 10000, value // 100 % 100, value % 100)


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    index = d.year * 12 + d.month - 1 + n
    year, month0 = divmod(index, 12)
    last = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(d.day, last))


# O'zbekiston: UTC+5, yozgi vaqt yo'q (1992-yildan).
TASHKENT = timezone(timedelta(hours=5), "Asia/Tashkent")


def today_tashkent(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(TASHKENT).date()
