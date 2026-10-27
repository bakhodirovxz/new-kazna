"""fact_investment (obyekt × oy, sana — oyning 1-kuni) va fact_object_stage — prototip «investments
(Адреса)»: 14 obyekt, yillik reja 2025 — 0,8 × 2026 rejasi, oylik og'irliklar 0,6 + 0,08 × oy,
fakt = reja × obyekt koeffitsienti (0,62–1,05) × tebranish, joriy oy — o'tgan kunlar ulushi.

Ochilish (OPEN_DOC, tarix boshi) — obyektning 2025 yilgacha to'plangan moliyalashtirishi, umumiy
qiymatdan oshmasligi uchun cheklangan. КС-2 foizi = min(0,98; moliyaviy bajarilish × koeff).
Avans: 2026 yil mart–avgustda berilib, 60–200 kundan keyin yopiladi (qoldiq oy oxirida).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, FUNDS, OBJECTS
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

MONTH_DOC = "aip_month"
OPEN_DOC = "aip_opening"
STAGE_DOC = "aip_stage"
STAGES = ("Проектно-сметная документация", "Экспертиза", "Тендер и договор",
          "Строительно-монтажные работы", "Поставка оборудования", "Пусконаладка",
          "Ввод в эксплуатацию")
YEAR_SHARE = {2025: 0.8, 2026: 1.0}
_WEIGHTS = [0.6 + m * 0.08 for m in range(12)]
_PCT = Decimal("0.0001")


def annual_plan(n: int, year: int) -> float:
    return OBJECTS[n - 1][5] * 1000 * YEAR_SHARE.get(year, 0.0)


def monthly_plan(n: int, month: date) -> float:
    return annual_plan(n, month.year) * _WEIGHTS[month.month - 1] / sum(_WEIGHTS)


def opening(model: SynthModel, n: int) -> float:
    total, plan = OBJECTS[n - 1][4] * 1000, OBJECTS[n - 1][5] * 1000
    cap = total - 1.2 * 1.8 * plan  # 2025–2026 faktining yuqori chegarasi
    return max(0.0, min(total * rnd(model.seed, "invopen", n).uniform(0.1, 0.3), cap))


def _fact(model: SynthModel, n: int, month: date) -> float:
    if month > model.as_of:
        return 0.0
    ratio = rnd(model.seed, "invratio", n).uniform(0.62, 1.05)
    value = monthly_plan(n, month) * ratio * rnd(model.seed, "invfact", n,
                                                  month_id(month)).uniform(0.88, 1.12)
    if (month.year, month.month) == (model.as_of.year, model.as_of.month):
        value *= model.as_of.day / calendar.monthrange(month.year, month.month)[1]
    return value


def _months(model: SynthModel) -> list[date]:
    return [date(y, m, 1) for y in sorted(YEAR_SHARE) if y <= model.as_of.year
            for m in range(1, 13)]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    inv = stages = 0
    for n, (_name, b, _kind, src, total_bn, _plan, _deadline) in enumerate(OBJECTS, start=1):
        code, branch, total = f"OBJ-{n:02d}", BRANCHES[b].code, total_bn * 1000
        base = {"branch_code": branch, "object_code": code, "source_code": FUNDS[src][0]}
        start = opening(model, n)
        if model.history_start >= window.date_from:
            sink.add("fact_investment", {
                **base, "doc_type": OPEN_DOC, "src_id": f"OPEN-{n:02d}",
                "date_id": date_id(model.history_start), "plan": money(0), "fact": money(start),
                "physical_pct": None, "advance": money(0), "advance_date_id": None})
            inv += 1
        ar = rnd(model.seed, "adv", n)
        issued = date(2026, ar.randint(3, 8), ar.randint(1, 28))
        amount = annual_plan(n, 2026) * ar.uniform(0.0, 0.08)
        closed = issued + timedelta(days=ar.randint(60, 200))
        phys_k = rnd(model.seed, "phys", n).uniform(0.72, 1.02)
        cumulative = start
        for month in _months(model):
            fact = _fact(model, n, month)
            cumulative += fact
            elapsed = month <= model.as_of
            end = model.period_end(month) if elapsed else month
            open_adv = elapsed and issued <= end < closed and amount >= 0.01
            if month < window.date_from.replace(day=1):
                continue
            phys = (Decimal(str(min(0.98, cumulative / total * phys_k))).quantize(_PCT)
                    if elapsed else None)
            sink.add("fact_investment", {
                **base, "doc_type": MONTH_DOC, "src_id": f"INV-{n:02d}-{month_id(month)}",
                "date_id": date_id(month), "plan": money(monthly_plan(n, month)),
                "fact": money(fact), "physical_pct": phys,
                "advance": money(amount if open_adv else 0),
                "advance_date_id": date_id(issued) if open_adv else None})
            inv += 1
        sr = rnd(model.seed, "stages", n)
        done_upto = int(sr.uniform(2.2, 6.4))
        for k, stage_name in enumerate(STAGES):
            planned = date(2026, min(12, k + 2), 15)
            actual = planned + timedelta(days=sr.randint(-10, 40))
            done = k <= done_upto and actual <= model.as_of
            if planned < window.date_from:
                continue
            sink.add("fact_object_stage", {
                "doc_type": STAGE_DOC, "src_id": f"STG-{n:02d}-{k + 1}",
                "date_id": date_id(planned), "branch_code": branch, "object_code": code,
                "stage_no": k + 1, "stage_name": stage_name,
                "fact_date_id": date_id(actual) if done else None})
            stages += 1
    return {"fact_investment": inv, "fact_object_stage": stages}
