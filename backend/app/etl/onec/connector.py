"""OneCConnector — SourceConnector (spec 5.2) 1C `hs/aiassistant` ustida (S1 spec 3).

Moslashtirish:
  /payments (har tashkilot org_uid bilan) → fact_cashflow (out), dim_item, dim_counterparty
  /income (faqat onec.income_enabled)    → fact_cashflow (in); tashkilot nomi → filial
  /budget {Mode: plan} (oyna yillari)    → fact_payment_plan (oylik reja, 1-kun)
Statya/kontragent kodlari — normallashtirilgan nomdan barqaror xesh (1C UID bermaydi, G7).
Moslashtirilmagan tashkilot "1C:<nom>" kodi bilan yuboriladi → merge `missing_branch` →
sifat tekshiruvi 3 publish'ni to'xtatadi (jim yo'qotish yo'q).
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from app.core.logging import get_logger
from app.dwh.dates import date_id, today_tashkent
from app.etl.onec.client import OneCClient, OneCTruncatedError
from app.etl.onec.models import BudgetPlanResponse, IncomeResponse, PaymentsResponse, parse
from app.etl.types import (
    ConnectorUnavailableError,
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "onec"
MLN = Decimal(1_000_000)
CENT = Decimal("0.01")
log = get_logger("ugekazna.onec")


@dataclass(frozen=True, slots=True)
class OrgMap:
    branch_code: str
    org_uid: str
    org_name: str


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def stable_code(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(_norm(p) for p in parts).encode()).hexdigest()
    return prefix + digest[:12]


def to_mln(amount: Decimal) -> Decimal:
    return (amount / MLN).quantize(CENT, rounding=ROUND_HALF_EVEN)


def unmapped_branch(org_name: str) -> str:
    return f"1C:{org_name}"


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


class OneCConnector:
    def __init__(self, client: OneCClient, orgs: Sequence[OrgMap], *,
                 income_enabled: bool = False, page_limit: int = 100_000,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = SOURCE
        # M9: Runner javobni xotiraga yig'adi; DB tranzaksiyasi 1C kutilgandan keyin ochiladi.
        self.buffered = True
        self.client = client
        self.orgs = list(orgs)
        self.income_enabled = income_enabled
        self.page_limit = page_limit
        self.now = now
        self._by_name = {_norm(o.org_name): o for o in self.orgs}

    # ── Protokol ────────────────────────────────────────────────────
    def healthcheck(self) -> HealthResult:
        today = _ymd(today_tashkent())
        try:
            self.client.post("/payments", {"org_uid": self.orgs[0].org_uid, "date_from": today,
                                           "date_to": today, "limit": 1})
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        note = " (HTTP без TLS — см. ONEC_ALLOW_HTTP)" if self.client.insecure else ""
        if self.client.insecure:
            log.warning("onec_insecure_http")
        return HealthResult(True, "1С доступна" + note)

    def watermark(self) -> Watermark:
        # 1C javobida o'zgarish vaqti yo'q (G9): yuklash boshlangan vaqt.
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None  # 5110/5210/5530 oborotlari 1C servisida yo'q (G3)

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        counts: Counter[str] = Counter({"fact_cashflow": 0, "fact_payment_plan": 0})
        items: dict[str, dict[str, Any]] = {}
        cps: dict[str, dict[str, Any]] = {}
        self._payments(window, sink, counts, items, cps)
        if self.income_enabled:
            self._income(window, sink, counts, items)
        self._budget(window, sink, counts, items)
        for row in items.values():
            sink.add("dim_item", row)
        for row in cps.values():
            sink.add("dim_counterparty", row)
        counts["dim_item"] = len(items)
        counts["dim_counterparty"] = len(cps)
        return ExtractStats(sum(counts.values()), dict(counts))

    # ── Yordamchilar ────────────────────────────────────────────────
    def _branch(self, org_name: str) -> str:
        org = self._by_name.get(_norm(org_name))
        return org.branch_code if org else unmapped_branch(org_name)

    @staticmethod
    def _item(direction: str, name: str, items: dict[str, dict[str, Any]]) -> str:
        code = stable_code("1C-O-" if direction == "out" else "1C-I-", name)
        items.setdefault(code, {"code": code, "name": name[:300], "activity": "operating",
                                "direction": direction, "sort_order": 900})
        return code

    def _payments(self, window: Window, sink: StagingSink, counts: Counter[str],
                  items: dict[str, dict[str, Any]], cps: dict[str, dict[str, Any]]) -> None:
        for org in self.orgs:
            data = self.client.post("/payments", {
                "org_uid": org.org_uid, "date_from": _ymd(window.date_from),
                "date_to": _ymd(window.date_to), "limit": self.page_limit})
            response = parse(PaymentsResponse, data, "/payments")
            if len(response.payments) >= self.page_limit:
                raise OneCTruncatedError(
                    f"1С /payments ({org.branch_code}): {len(response.payments)} строк = limit, "
                    "данные могут быть неполными — нужна постраничная выдача (G9)")
            for p in response.payments:
                if p.amount <= 0 or not window.contains(p.doc_date):
                    log.warning("onec_payment_skipped", branch=org.branch_code, number=p.number,
                                reason="non_positive" if p.amount <= 0 else "outside_window")
                    continue
                row: dict[str, Any] = {
                    "doc_type": "onec_payment",
                    "src_id": f"{org.org_uid}:{p.number}:{p.doc_date.isoformat()}",
                    "date_id": date_id(p.doc_date), "branch_code": org.branch_code,
                    "item_code": self._item("out", p.expense_type_name, items),
                    "direction": "out", "amount": to_mln(p.amount),
                }
                if p.contractor_name:
                    code = stable_code("1C-CP-", p.contractor_name)
                    cps.setdefault(code, {"code": code, "name": p.contractor_name,
                                          "kind": "supplier"})
                    row["cp_code"] = code
                sink.add("fact_cashflow", row)
                counts["fact_cashflow"] += 1

    def _income(self, window: Window, sink: StagingSink, counts: Counter[str],
                items: dict[str, dict[str, Any]]) -> None:
        data = self.client.post("/income", {"DateFrom": _ymd(window.date_from),
                                            "DateTo": _ymd(window.date_to),
                                            "Limit": self.page_limit})
        response = parse(IncomeResponse, data, "/income")
        if len(response.items) >= self.page_limit:
            raise OneCTruncatedError("1С /income: строк = limit (G9)")
        seen: Counter[tuple[str, ...]] = Counter()
        for r in response.items:
            if r.amount <= 0 or not window.contains(r.doc_date):
                continue
            branch = self._branch(r.org_name)
            item = self._item("in", r.direction_name, items)
            amount = to_mln(r.amount)
            key = (branch, r.doc_date.isoformat(), item, str(amount))
            ordinal = seen[key]
            seen[key] += 1
            # Hujjat raqami yo'q (G8): kalit — maydonlar + tartib raqami.
            sink.add("fact_cashflow", {
                "doc_type": "onec_income", "src_id": ":".join((*key, str(ordinal))),
                "date_id": date_id(r.doc_date), "branch_code": branch, "item_code": item,
                "direction": "in", "amount": amount})
            counts["fact_cashflow"] += 1

    def _budget(self, window: Window, sink: StagingSink, counts: Counter[str],
                items: dict[str, dict[str, Any]]) -> None:
        for year in range(window.date_from.year, window.date_to.year + 1):
            data = self.client.post("/budget", {"Year": year, "Mode": "plan"})
            response = parse(BudgetPlanResponse, data, "/budget")
            totals: defaultdict[tuple[str, str, int], Decimal] = defaultdict(Decimal)
            for r in response.items:
                item = self._item("out", r.expense_type_name, items)
                totals[(self._branch(r.org_name), item, r.month)] += r.plan_sum
            for (branch, item, month), amount in sorted(totals.items()):
                sink.add("fact_payment_plan", {
                    "doc_type": "onec_budget_plan",
                    "src_id": f"{year}{month:02d}:{branch}:{item}",
                    "date_id": date_id(date(year, month, 1)), "branch_code": branch,
                    "item_code": item, "amount": to_mln(amount)})
                counts["fact_payment_plan"] += 1
