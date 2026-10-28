"""Tasdiqlangan paketning nashr holati -- o'qilganda HISOBLANADI (saqlanmaydi, o'zgarmaydi).

Qo'lda nashr har yugurishda BARCHA tasdiqlangan boshlarni to'liq o'qiydi, shuning uchun paketni
`etl_request_id >= o'z so'rovi` bo'lgan har qanday qo'lda yugurish qamrab oladi (tasdiqlangan
ma'lumot hech qachon avtomatik o'chirilmaydi/qaytarilmaydi):
- shu oraliqda muvaffaqiyatli yugurish bor -> «опубликовано»;
- aks holda ishlayotgan so'rov bor -> «публикуется»;
- aks holda eng yangi tugagan qamrab oluvchi yugurish yiqilgan -> «ошибка» (sabab + tafsilot);
- aks holda -> «ожидает».
Tuzatish -- mavjud maker-checker oqimi: tuzatuvchi yoki o'chiruvchi yangi paket; tasdig'idan keyin
yangi qo'lda yugurish tuzatilgan boshlarni o'qiydi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.manual.schemas import PublicationCheck, PublicationOut

ERROR_MAX = 300
DETAIL_MAX = 10
_DETAIL_KEYS = ("branch_id", "month_id", "date_id")  # faqat identifikatorlar, summalarsiz


@dataclass(frozen=True, slots=True)
class State:
    published_through: int  # eng katta muvaffaqiyatli qo'lda so'rov id'si (0 -- yo'q)
    running: int  # ishlayotgan so'rov id'si (0 -- yo'q)
    finished: int  # eng yangi tugagan (done/failed) so'rov id'si (0 -- yo'q)
    finished_failed: bool
    run_id: int | None
    run_status: str | None
    run_error: str | None
    request_error: str | None


def state(db: Session) -> State:
    published = db.execute(text(
        "SELECT coalesce(max(r.id), 0) FROM core.etl_requests r JOIN core.etl_run u "
        "ON u.id = r.run_id WHERE r.source = 'manual' AND r.status = 'done' "
        "AND u.status = 'success'")).scalar_one()
    running = db.execute(text(
        "SELECT coalesce(max(id), 0) FROM core.etl_requests "
        "WHERE source = 'manual' AND status = 'running'")).scalar_one()
    last = db.execute(text(
        "SELECT r.id, r.status, r.error, r.run_id, u.status AS run_status, u.error AS run_error "
        "FROM core.etl_requests r LEFT JOIN core.etl_run u ON u.id = r.run_id "
        "WHERE r.source = 'manual' AND r.status IN ('done', 'failed') "
        "ORDER BY r.id DESC LIMIT 1")).first()
    if last is None:
        return State(int(published), int(running), 0, False, None, None, None, None)
    ok = last.status == "done" and last.run_status == "success"
    return State(int(published), int(running), int(last.id), not ok, last.run_id,
                 last.run_status, last.run_error, last.error)


def status_of(s: State, request_id: int) -> str:
    if request_id <= s.published_through:
        return "published"
    if s.running >= request_id:
        return "running"
    if s.finished >= request_id and s.finished_failed:
        return "failed"
    return "queued"


def failed_filter(s: State) -> tuple[str, dict[str, Any]]:
    """`status=failed` filtri: status_of() bilan bir xil qoida, SQL ko'rinishida."""
    if not s.finished_failed:
        return "FALSE", {}
    return ("(etl_request_id IS NOT NULL AND etl_request_id > :ms AND etl_request_id <= :nf "
            "AND NOT :rn >= etl_request_id)",
            {"ms": s.published_through, "nf": s.finished, "rn": s.running})


def brief(s: State, status: str, request_id: int | None) -> PublicationOut | None:
    """Ro'yxat uchun: holat va (xatoda) qisqa sabab, qo'shimcha so'rovlarsiz."""
    if status != "approved" or request_id is None:
        return None
    st = status_of(s, request_id)
    out = PublicationOut(status=st)
    if st == "failed":
        out.run_id = s.run_id
        out.kind = "quality" if s.run_status == "failed_quality" else "build"
        out.error = (s.run_error or s.request_error or "")[:ERROR_MAX] or None
    return out


def _checks(db: Session, run_id: int, branch_id: int) -> list[PublicationCheck]:
    detail = db.execute(text(
        "SELECT detail FROM core.etl_step WHERE run_id = :r AND name = 'quality'"),
        {"r": run_id}).scalar_one_or_none()
    out: list[PublicationCheck] = []
    for code, body in sorted((detail or {}).items()):
        if not isinstance(body, dict) or body.get("ok", True):
            continue
        items = [{k: int(v[k]) for k in _DETAIL_KEYS if k in v}
                 for v in body.get("violations", []) if isinstance(v, dict)
                 and v.get("branch_id") == branch_id][:DETAIL_MAX]  # faqat o'z filiali
        out.append(PublicationCheck(code=code, items=items))
    return out


def detail(db: Session, s: State, batch: Any) -> PublicationOut:
    """Paket sahifasi uchun: sabab, tekshiruv nomi va (o'z filiali bo'yicha) buzilishlar."""
    if batch.status != "approved" or batch.etl_request_id is None:
        return PublicationOut(status="none")
    out = brief(s, batch.status, batch.etl_request_id) or PublicationOut(status="none")
    if out.status == "published":
        out.build_id = db.execute(text(
            "SELECT u.build_id FROM core.etl_requests r JOIN core.etl_run u ON u.id = r.run_id "
            "WHERE r.source = 'manual' AND r.status = 'done' AND u.status = 'success' "
            "AND r.id >= :i ORDER BY r.id LIMIT 1"),
            {"i": batch.etl_request_id}).scalar_one_or_none()
    elif out.status == "failed" and out.kind == "quality" and s.run_id is not None:
        out.checks = _checks(db, s.run_id, batch.branch_id)
    return out
