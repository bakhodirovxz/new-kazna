"""Valyuta hisoblari summalarini so'mga o'girish uchun ЦБ kursi (dwh.fx_rate, S2 spec 3.2).

Kurs `day` dan ko'pi bilan MAX_FX_AGE_DAYS kun eski bo'lishi kerak — eskirgan kurs jimgina
ishlatilmaydi (hisob-kun `fx_rate_missing` bilan rad etiladi).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import text

from app.dwh.dates import date_id
from app.etl.db import etl_transaction

MAX_FX_AGE_DAYS = 10


class FxLookup(Protocol):
    def rate(self, currency: str, day: date) -> Decimal | None: ...


class DbFxLookup:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], Decimal | None] = {}

    def rate(self, currency: str, day: date) -> Decimal | None:
        if currency == "UZS":
            return Decimal(1)
        key = (currency, date_id(day))
        if key not in self._cache:
            with etl_transaction() as conn:
                value = conn.execute(text(
                    "SELECT rate FROM dwh.fx_rate WHERE currency = :c AND date_id <= :d "
                    "AND date_id >= :lo ORDER BY date_id DESC LIMIT 1"),
                    {"c": currency, "d": date_id(day),
                     "lo": date_id(day - timedelta(days=MAX_FX_AGE_DAYS))}).scalar_one_or_none()
            self._cache[key] = None if value is None else Decimal(value)
        return self._cache[key]
