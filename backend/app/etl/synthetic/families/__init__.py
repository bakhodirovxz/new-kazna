"""Sintetik fakt oilalari reyestri. Keyingi rejalar (generation, energy_sales, procurement,
stock, stock_move, investment, loan_schedule, hr) o'z modulini yozib shu ro'yxatga qo'shadi."""

from __future__ import annotations

from collections.abc import Callable

from app.etl.synthetic.families import (
    calendar,
    cash,
    debt,
    dims,
    funds,
    fx,
    hr,
    investment,
    loans,
    outlook,
    payments,
    procurement,
    production,
    stock,
)
from app.etl.synthetic.model import SynthModel
from app.etl.types import StagingSink, Window

Family = Callable[[SynthModel, Window, StagingSink], dict[str, int]]

FAMILIES: list[tuple[str, Family]] = [
    ("dims", dims.generate),
    ("fx", fx.generate),
    ("cash", cash.generate),
    ("payments", payments.generate),
    ("debt", debt.generate),
    ("funds", funds.generate),
    ("calendar", calendar.generate),
    ("loans", loans.generate),
    ("procurement", procurement.generate),
    ("investment", investment.generate),
    ("aip_outlook", outlook.generate),
    ("hr", hr.generate),
    ("production", production.generate),
    ("stock", stock.generate),
]
