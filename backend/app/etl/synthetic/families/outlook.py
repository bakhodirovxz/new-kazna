"""fact_investment — АИП rejasining kelgusi yillari (dev/test sintetikasi, S5 финмодель uchun).

S4 `investment` oilasi rejani faqat joriy yil oxirigacha beradi; финмодель 2027+ yillar
investitsiyalarini ham talab qiladi. Har obyekt uchun keyingi 3 yil (2032 dan oshmay) rejasi —
joriy yil rejasining 0,8 / 0,6 / 0,4 ulushi, yil 1-yanvari qatorida (fakt 0). Deterministik.
"""

from __future__ import annotations

from datetime import date

from app.dwh.dates import date_id
from app.etl.synthetic.families.investment import annual_plan
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, FUNDS, OBJECTS
from app.etl.types import StagingSink, Window

OUTLOOK_DOC = "aip_outlook"
SHARES = (0.8, 0.6, 0.4)
LAST_YEAR = 2032


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    base_year = model.as_of.year
    for n, (_name, b, _kind, src, _total, _plan, _deadline) in enumerate(OBJECTS, start=1):
        for step, share in enumerate(SHARES, start=1):
            year = base_year + step
            if year > LAST_YEAR:
                break
            day = date(year, 1, 1)
            if day < window.date_from:
                continue
            sink.add("fact_investment", {
                "doc_type": OUTLOOK_DOC, "src_id": f"OUT-{n:02d}-{year}",
                "date_id": date_id(day), "branch_code": BRANCHES[b].code,
                "object_code": f"OBJ-{n:02d}", "source_code": FUNDS[src][0],
                "plan": money(annual_plan(n, base_year) * share), "fact": money(0),
                "physical_pct": None, "advance": money(0), "advance_date_id": None})
            count += 1
    return {"fact_investment": count}
