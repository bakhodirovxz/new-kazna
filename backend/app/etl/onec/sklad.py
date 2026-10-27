"""OneCSkladConnector — SourceConnector 1C `hs/sklad/materials` ustida (S3 spec 3.3).

Har tashkilot (onec.orgs) × har oy: {date_from: oy boshi, date_to: min(oy oxiri, oyna oxiri),
org_uid} → oy oxiri (ochiq oyda — bugun) snapshot'i: fact_stock (value = closing / 10⁶),
kengaytirilgan javobda — fact_stock_move (debit → prixod, credit → rasxod). `isTotal`/`1000`
jami qatorlari tashlanadi (ikki marta sanalmaydi); manfiy qoldiq (сторно) — log, yuklanmaydi.
Oyna — oxirgi `months` oy (Runner `lookback_months`), maqsadlar oyna ichida to'liq almashtiriladi.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.logging import get_logger
from app.dwh.dates import add_months, date_id, month_end, month_id, month_start, today_tashkent
from app.etl.onec.client import OneCClient
from app.etl.onec.connector import OrgMap, stable_code, to_mln
from app.etl.onec.sklad_models import MaterialRow, parse_materials
from app.etl.types import (
    ConnectorUnavailableError,
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "onec_sklad"
PATH = "/materials"
TOTAL_ACCOUNT = "1000"
DEFAULT_WAREHOUSE = "Основной склад"
_QTY = Decimal("0.001")
log = get_logger("ugekazna.onec.sklad")


def periods(window: Window) -> list[tuple[date, date]]:
    """To'liq oylar (oborotlar oy bo'yicha to'liq bo'lsin), oxirgisi oyna oxirida kesiladi."""
    out: list[tuple[date, date]] = []
    cur = month_start(window.date_from)
    while cur <= window.date_to:
        out.append((cur, min(month_end(cur), window.date_to)))
        cur = add_months(cur, 1)
    return out


class OneCSkladConnector:
    def __init__(self, client: OneCClient, orgs: Sequence[OrgMap], *, months: int = 13,
                 source: str = SOURCE,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.client = client
        self.orgs = list(orgs)
        self.lookback_months = months
        self.now = now
        self._fetched: list[tuple[OrgMap, date, list[MaterialRow]]] | None = None

    def healthcheck(self) -> HealthResult:
        today = today_tashkent().isoformat()
        try:
            self.client.post(PATH, {"date_from": today, "date_to": today,
                                    "org_uid": self.orgs[0].org_uid})
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "1С (склад) доступна")

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def prefetch(self, window: Window) -> None:
        """Barcha /materials javoblari DB tranzaksiyasidan TASHQARIDA olinadi (Runner chaqiradi)."""
        self._fetched = [
            (org, end, parse_materials(self.client.post(PATH, {
                "date_from": start.isoformat(), "date_to": end.isoformat(),
                "org_uid": org.org_uid})).data)
            for org in self.orgs for start, end in periods(window)]

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if self._fetched is None:
            self.prefetch(window)
        fetched, self._fetched = self._fetched or [], None
        counts: Counter[str] = Counter({"fact_stock": 0, "fact_stock_move": 0})
        noms: dict[str, dict[str, Any]] = {}
        for org, end, rows in fetched:
            for row in rows:
                self._row(org, end, row, sink, counts, noms)
        for nom in noms.values():
            sink.add("dim_nomenclature", nom)
        counts["dim_nomenclature"] = len(noms)
        return ExtractStats(sum(counts.values()), dict(counts))

    @staticmethod
    def _row(org: OrgMap, end: date, row: MaterialRow, sink: StagingSink,
             counts: Counter[str], noms: dict[str, dict[str, Any]]) -> None:
        if row.is_total or row.account_code == TOTAL_ACCOUNT:
            return
        if row.closing < 0:
            log.warning("onec_sklad_negative_balance", branch=org.branch_code,
                        account=row.account_code)
            return
        if row.nomenclature_code or row.nomenclature_name:
            nom_code = stable_code("1C-N-", row.nomenclature_code or row.nomenclature_name or "",
                                   row.unit or "")
            name = row.nomenclature_name or row.account_name
        else:
            nom_code = f"1C-ACC-{row.account_code}"
            name = row.account_name
        noms.setdefault(nom_code, {"code": nom_code, "name": name[:300],
                                   "category": row.account_name[:100],
                                   "unit": (row.unit or "—")[:16], "enbt_code": None})
        warehouse = (row.warehouse_name or DEFAULT_WAREHOUSE).strip()[:100] or DEFAULT_WAREHOUSE
        wh_key = hashlib.sha256(warehouse.encode()).hexdigest()[:10]
        key = f"{org.org_uid}:{nom_code}:{wh_key}:{month_id(end)}"
        value = to_mln(row.closing)
        qty = (row.closing_qty or Decimal(0)).quantize(_QTY)
        base = {"date_id": date_id(end), "branch_code": org.branch_code, "nom_code": nom_code}
        if value > 0 or qty > 0:
            sink.add("fact_stock", {
                **base, "doc_type": "onec_stock", "src_id": key, "warehouse": warehouse,
                "qty": qty, "value": value, "min_qty": row.min_qty,
                "last_move_date_id": date_id(row.last_move_date) if row.last_move_date else None})
            counts["fact_stock"] += 1
        for direction, amount in (("in", row.debit_sum), ("out", row.credit_sum)):
            if amount is not None and amount > 0:
                sink.add("fact_stock_move", {
                    **base, "doc_type": "onec_stock_move", "src_id": f"{key}:{direction}",
                    "direction": direction, "qty": Decimal("0.000"), "value": to_mln(amount)})
                counts["fact_stock_move"] += 1
