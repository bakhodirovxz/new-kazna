"""ProcurementConnector — SourceConnector (S4 spec 3.1): ProcurementPortal lotlari → kanonik
fact_procurement qatorlari (+ dim_counterparty, dim_nomenclature).

Buyurtmachi INN → filial (dim_branch.inn xaritasi, make_connector to'ldiradi); usul nomi → kod
(noma'lum → «other» + ogohlantirish); holat nomi → kod (noma'lum → xato, qator o'tkaziladi).
Qator sanasi: tuzilgan — shartnoma sanasi, qolganlari — e'lon sanasi. Jismoniy shaxs/YaTT
(14 xonali INN) — CP-FL «Физическое лицо», ismi hech qayerga yozilmaydi (TZ 9). Upsert.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from app.etl.keys import normalize_name, stable_code, to_mln
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)
from app.etl.zakupki.codes import DONE, INDIVIDUAL_CP, INDIVIDUAL_NAME
from app.etl.zakupki.portal import PortalLot, ProcurementPortal, method_code, status_code

SOURCE = "xarid"
DOC_TYPE = "portal_lot"
ERROR_TARGET = "procurement_portal"
_PINFL = re.compile(r"^\d{14}$")


class ProcurementConnector:
    def __init__(self, portal: ProcurementPortal, branches: Mapping[str, str], *,
                 source: str = SOURCE,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.portal = portal
        self.branches = dict(branches)
        self.now = now

    def healthcheck(self) -> HealthResult:
        return self.portal.healthcheck()

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("ProcurementConnector uchun ReportingSink kerak (xatolar jurnali)")
        cps: dict[str, dict[str, Any]] = {}
        noms: dict[str, dict[str, Any]] = {}
        rows = 0
        for lot in self.portal.lots(window):
            row = self._row(lot, sink, cps, noms)
            if row is None or not window.contains_id(int(row["date_id"])):
                continue
            sink.add("fact_procurement", row)
            rows += 1
        for cp in cps.values():
            sink.add("dim_counterparty", cp)
        for nom in noms.values():
            sink.add("dim_nomenclature", nom)
        return ExtractStats(rows, {})

    def _row(self, lot: PortalLot, sink: ReportingSink, cps: dict[str, dict[str, Any]],
             noms: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        no = lot.lot_no[:64]
        branch = self.branches.get(lot.customer_inn)
        if branch is None:
            sink.error(target=ERROR_TARGET, code="unknown_customer", src_id=no,
                       message=f"лот {no}: заказчик (ИНН) не сопоставлен с филиалом")
            return None
        status = status_code(lot.status)
        if status is None:
            sink.error(target=ERROR_TARGET, code="unknown_status", src_id=no,
                       message=f"лот {no}: неизвестный статус «{lot.status[:40]}»")
            return None
        method = method_code(lot.method)
        if method is None:
            sink.error(target=ERROR_TARGET, code="unknown_method", src_id=no, severity="warning",
                       message=f"лот {no}: способ «{lot.method[:40]}» учтён как «прочие»")
            method = "other"
        done = status == DONE
        if done and (lot.contract_date is None or lot.contract_price_uzs is None):
            sink.error(target=ERROR_TARGET, code="bad_row", src_id=no,
                       message=f"лот {no}: для заключённого договора нужны дата и цена договора")
            return None
        day = lot.contract_date if done and lot.contract_date else lot.announce_date
        cp_code = self._supplier(lot, cps) if done else None
        subject = lot.subject.strip()[:300] or "—"
        nom_code = stable_code("XR-S-", normalize_name(subject))
        noms.setdefault(nom_code, {"code": nom_code, "name": subject,
                                   "category": subject[:100], "unit": "—", "enbt_code": None})
        return {
            "doc_type": DOC_TYPE, "src_id": no, "date_id": int(day.strftime("%Y%m%d")),
            "branch_code": branch, "nom_code": nom_code, "cp_code": cp_code, "lot_no": no,
            "method": method, "status": status, "start_price": to_mln(lot.start_price_uzs),
            "contract_price": to_mln(lot.contract_price_uzs) if done and lot.contract_price_uzs
            is not None else None,
            "procedure_days": (day - lot.announce_date).days if done else None}

    @staticmethod
    def _supplier(lot: PortalLot, cps: dict[str, dict[str, Any]]) -> str | None:
        inn = (lot.supplier_inn or "").strip()
        if not inn:
            return None
        if _PINFL.fullmatch(inn):  # jismoniy shaxs / YaTT — shaxsiy ma'lumot saqlanmaydi
            cps.setdefault(INDIVIDUAL_CP, {"code": INDIVIDUAL_CP, "name": INDIVIDUAL_NAME,
                                           "kind": "supplier", "inn": None})
            return INDIVIDUAL_CP
        code = stable_code("XR-CP-", inn)
        name = (lot.supplier_name or inn).strip()[:300]
        cps.setdefault(code, {"code": code, "name": name, "kind": "supplier", "inn": inn})
        return code
