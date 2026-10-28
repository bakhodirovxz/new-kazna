"""Nashr xatosi: qo'lda kiritilgan paketlar sifat tekshiruvidan o'tmadi.

Ildiz sabab: ManualConnector HAR yugurishda BARCHA tasdiqlangan boshlarni to'liq o'qiydi, shuning
uchun bitta yomon paket keyingi barcha qo'lda nashrlarni yiqitardi. Yechim: yiqilgan yugurishga
kirgan, hali nashr qilinmagan paketlar `failed` («Ошибка публикации», sabab ko'rinadi) bo'ladi va
boshlar oxirgi NASHR QILINGAN tasdiqlangan versiyaga qaytadi; keyingi mustaqil paketlar nashr
qilinadi. Yangi tasdiq/versiya yaratilmaydi (SoD saqlanadi): tuzatish -- muallifning yangi paketi
va ikkinchi shaxsning tasdig'i. 1C tekshiruvlari o'zgarmaydi.
"""

from __future__ import annotations

from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, record
from app.etl.db import etl_transaction

ERROR_MAX = 300

# So'rovlar id tartibida bajariladi: id <= k ning hammasi shu yugurishgacha o'qilgan; muvaffaqiyatli
# yugurish bilan yopilmaganlari nashr qilinmagan.
_FAIL = text(
    "UPDATE core.manual_batch b SET status = 'failed', publish_error = :m, version = version + 1 "
    "WHERE b.status = 'approved' AND b.etl_request_id <= :k AND NOT EXISTS ("
    "  SELECT 1 FROM core.etl_requests r JOIN core.etl_run u ON u.id = r.run_id "
    "  WHERE r.id = b.etl_request_id AND u.status = 'success') "
    "RETURNING b.batch_id, b.entity, b.branch_id, b.rows")
_REVERT = text(
    "UPDATE core.manual_head h SET approved_version = p.version, "
    "approved_deleted = coalesce(p.deleted, false), updated_at = now() "
    "FROM (SELECT fe.entry_id, pv.version, pv.deleted "
    "      FROM (SELECT DISTINCT entry_id FROM core.manual_entry WHERE batch_id = ANY(:b)) fe "
    "      LEFT JOIN LATERAL (SELECT e.version, e.deleted FROM core.manual_entry e "
    "        JOIN core.manual_batch b ON b.batch_id = e.batch_id "
    "        WHERE e.entry_id = fe.entry_id AND b.status = 'approved' "
    "        ORDER BY e.version DESC LIMIT 1) pv ON true) p "
    "WHERE h.entry_id = p.entry_id")


def fail_unpublished(request_id: int, run_id: int | None, error: str) -> list[int]:
    """`request_id` yugurishi sifatdan yiqilganda chaqiriladi. Yiqilgan batch_id'lar qaytadi."""
    message = f"{error} (запуск №{run_id})"[:ERROR_MAX]
    with etl_transaction() as conn:
        failed = conn.execute(_FAIL, {"m": message, "k": request_id}).all()
        ids = sorted(int(r.batch_id) for r in failed)
        if ids:
            conn.execute(_REVERT, {"b": ids})
    for r in failed:
        record(AuditEvent(
            action=AuditAction.DATA_BATCH_PUBLISH_FAILED, result="fail",
            object_type="manual_batch", object_id=str(r.batch_id),
            details={"batch_id": int(r.batch_id), "entity": r.entity, "branch_id": r.branch_id,
                     "rows": r.rows, "etl_request_id": request_id, "run_id": run_id,
                     "error": message}), role="etl")
    return ids
