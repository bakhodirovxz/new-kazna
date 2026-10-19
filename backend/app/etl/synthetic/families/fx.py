"""ЦБ РУз kurslari (sintetik): USD, EUR, CNY → so'm, har kun."""

from __future__ import annotations

import math
from datetime import timedelta

from app.dwh.dates import date_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    day = window.date_from
    last = min(window.date_to, model.as_of)
    while day <= last:
        t = (day - model.history_start).days
        noise = rnd(model.seed, "fx", day.isoformat()).uniform(-12, 12)
        usd = 12500 + 380 * math.sin(2 * math.pi * t / 365) + 0.25 * t + noise
        rates = {"USD": usd, "EUR": usd * (1.08 + 0.02 * math.sin(t / 90)), "CNY": usd / 7.2}
        for currency, rate in rates.items():
            sink.add("fx_rate", {"currency": currency, "date_id": date_id(day),
                                 "rate": money(rate)})
            count += 1
        day += timedelta(days=1)
    return {"fx_rate": count}
