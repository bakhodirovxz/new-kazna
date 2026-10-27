"""ManualConnector: «Ввод данных» da tasdiqlangan yozuvlar -> staging (spec 3.3).

`dwh`/`mart` ga qo'lda kiritish FAQAT shu konnektor + Runner orqali tushadi. Tasdiqlangan joriy
versiyalar (`approved_version`, o'chirilmagan) o'qiladi; to'liq almashtirish: `by_target` BARCHA
qo'lda kiritiladigan maqsadlarni (0 qatorlilarni ham) beradi, shuning uchun o'chirilgan yozuv
`dwh` dan `src_system='manual'` doirasida ketadi. Sezgir maydon `keystore.decrypt_str` bilan
ochiladi va `DbStagingSink.add -> protect()` darhol dwh AAD bilan qayta shifrlaydi: ochiq qiymat
faqat shu funksiya xotirasida, hech qachon log/xatoga tushmaydi.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core import keystore
from app.core.crypto import Purpose
from app.dwh.targets import DIM_TARGETS, TARGETS
from app.etl.db import etl_transaction
from app.etl.types import ControlTotals, ExtractStats, HealthResult, StagingSink, Watermark, Window
from app.manual.entities import ENTITIES, MANUAL_TARGETS, payload_for_target

_ENC_COLUMN = {Purpose.BANK: "bank_enc", Purpose.PII: "pii_enc"}
_ORDER = {name: i for i, name in enumerate(DIM_TARGETS)}


class ManualConnector:
    source = "manual"

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "manual")

    def watermark(self) -> Watermark:
        with etl_transaction() as conn:
            value = conn.execute(text(
                "SELECT max(decided_at) FROM core.manual_batch WHERE status = 'approved'"
            )).scalar()
        return Watermark(value)

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        by_target = dict.fromkeys(sorted(MANUAL_TARGETS), 0)
        with etl_transaction() as conn:  # scope_all: barcha filiallar
            # Faqat HAQIQATAN tasdiqlangan paket versiyalari (trigger'dan mustaqil 2-qatlam):
            # status='approved', tasdiqlovchi != kiritgan; mos kelmasa yugurish yiqiladi.
            rows = conn.execute(text(
                "SELECT h.entity, h.code, e.id, e.payload, e.bank_enc, e.pii_enc, h.entry_id, "
                "(b.status = 'approved' AND b.decided_by IS NOT NULL "
                " AND b.decided_by <> b.created_by) AS trusted, h.approved_deleted "
                "FROM core.manual_head h JOIN core.manual_entry e "
                "ON e.entry_id = h.entry_id AND e.version = h.approved_version "
                "JOIN core.manual_batch b ON b.batch_id = e.batch_id "
                "WHERE h.approved_version IS NOT NULL ORDER BY h.entry_id")).mappings().all()
            orphans = conn.execute(text(
                "SELECT count(*) FROM core.manual_head h WHERE h.approved_version IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM core.manual_entry e "
                "WHERE e.entry_id = h.entry_id AND e.version = h.approved_version)")).scalar_one()
        bad = int(orphans) + sum(1 for r in rows if not r["trusted"])
        if bad:
            # xabar -- faqat son (qiymatlarsiz)
            raise RuntimeError(f"manual: {bad} unapproved version(s) referenced")
        rows = [r for r in rows if not r["approved_deleted"]]
        # o'lchovlar faktlardan oldin (merge ham shunday tartibda, bu faqat o'qilishi uchun)
        rows = sorted(rows, key=lambda r: _ORDER.get(ENTITIES[r["entity"]].target, 99)
                      if r["entity"] in ENTITIES else 99)
        for r in rows:
            entity = ENTITIES.get(r["entity"])
            if entity is None:  # reyestrdan olib tashlangan obyekt -- o'tkazib yuboriladi
                continue
            values: dict[str, Any] = dict(r["payload"])
            for f in entity.secrets:
                assert f.purpose is not None
                col = _ENC_COLUMN[f.purpose]
                blob = r[col]
                if blob is not None:
                    values[f.name] = keystore.decrypt_str(
                        f.purpose, bytes(blob), f"core.manual_entry.{col}:{r['id']}")
            row = payload_for_target(entity, values, entry_id=r["entry_id"], code=r["code"])
            if entity.kind == "fact":
                day = int(row["date_id"])
                forward = TARGETS[entity.target].forward and day > window.to_id
                if not (window.contains_id(day) or forward):
                    continue
            sink.add(entity.target, row)
            by_target[entity.target] += 1
        return ExtractStats(sum(by_target.values()), by_target)

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None
