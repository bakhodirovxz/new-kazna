"""Audit jurnalini ko'rish (faqat audit:read — administrator va ichki nazorat)."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin.schemas import Page
from app.audit.schemas import AuditOut, VerifyOut
from app.audit.service import AuditAction, ip_aad, log_event, verify_chain_snapshot
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core import keystore, ratelimit
from app.core.crypto import CryptoError, Purpose
from app.core.db import DB
from app.core.request_meta import Meta

router = APIRouter(prefix="/audit", tags=["audit"])
Auditor = Annotated[AuthContext, Depends(require_perm(Perm.AUDIT_READ))]
EXPORT_LIMIT = 50_000
DEFAULT_WINDOW = timedelta(days=30)
# R1-1: "=", "+", "-", "@" — Excel/LibreOffice formula triggers; tab/CR/LF — ham xavfli (ba'zi
# ilovalar katakni formula sifatida talqin qiladi), ham CSV qatorlarini buzishi mumkin.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class Filters:
    def __init__(
        self,
        from_ts: Annotated[datetime | None, Query()] = None,
        to_ts: Annotated[datetime | None, Query()] = None,
        user_id: Annotated[int | None, Query(gt=0)] = None,
        action: Annotated[str | None, Query(max_length=64, pattern=r"^[a-z_.]+$")] = None,
        result: Annotated[str | None, Query(pattern=r"^(ok|fail|denied)$")] = None,
    ) -> None:
        self.from_ts = from_ts or datetime.now(UTC) - DEFAULT_WINDOW
        self.to_ts = to_ts
        self.user_id = user_id
        self.action = action
        self.result = result

    def sql(self) -> tuple[str, dict[str, Any]]:
        clauses = ["a.ts >= :from_ts"]
        params: dict[str, Any] = {"from_ts": self.from_ts}
        if self.to_ts is not None:
            clauses.append("a.ts < :to_ts")
            params["to_ts"] = self.to_ts
        if self.user_id is not None:
            clauses.append("a.user_id = :user_id")
            params["user_id"] = self.user_id
        if self.action:
            clauses.append("a.action LIKE :action")
            params["action"] = self.action.replace("_", "\\_") + "%"
        if self.result:
            clauses.append("a.result = :result")
            params["result"] = self.result
        return " AND ".join(clauses), params

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_ts": self.from_ts.isoformat(),
            "to_ts": self.to_ts.isoformat() if self.to_ts else None,
            "user_id": self.user_id,
            "action": self.action,
            "result": self.result,
        }


_SELECT = (
    "SELECT a.id, a.ts, a.user_id, u.username, a.action, a.result, a.object_type, a.object_id, "
    "a.request_id, a.details, a.ip_enc FROM core.audit_log a "
    "LEFT JOIN core.users u ON u.id = a.user_id WHERE {where} "
    "ORDER BY a.id DESC LIMIT :limit OFFSET :offset"
)


def _ip(audit_id: int, blob: bytes | None) -> str | None:
    if blob is None:
        return None
    try:
        return keystore.decrypt_str(Purpose.AUDIT, blob, ip_aad(audit_id))
    except CryptoError:
        return None


def _rows(
    db: Session, where: str, params: dict[str, Any], limit: int, offset: int
) -> list[AuditOut]:
    bind = {**params, "limit": limit, "offset": offset}
    result = db.execute(text(_SELECT.format(where=where)), bind)
    return [
        AuditOut(
            id=r["id"], ts=r["ts"], user_id=r["user_id"], username=r["username"],
            action=r["action"], result=r["result"], object_type=r["object_type"],
            object_id=r["object_id"], request_id=r["request_id"], details=r["details"],
            ip=_ip(r["id"], r["ip_enc"]),
        )
        for r in result.mappings()
    ]


@router.get("")
def list_audit(
    ctx: Auditor,
    db: DB,
    filters: Annotated[Filters, Depends()],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[AuditOut]:
    where, params = filters.sql()  # R1-3: bitta marta hisoblanadi, count va _rows shuni ishlatadi
    # `where` is built only from fixed clause literals in Filters.sql() (never from raw
    # user input) and all values are bound params, so this is not an injection vector.
    count_sql = text(f"SELECT count(*) FROM core.audit_log a WHERE {where}")  # noqa: S608
    total = db.execute(count_sql, params).scalar_one()
    items = _rows(db, where, params, page_size, (page - 1) * page_size)
    return Page[AuditOut](items=items, total=int(total), page=page, page_size=page_size)


# R1-1: oddiy `startswith` faqat 0-pozitsiyani tekshirar edi — old belgisidan oldin bo'sh joy
# (yoki NBSP) qo'yilsa (masalan, " =1+1"), formula triggerni "yashirish" mumkin edi. Endi
# chap tomondagi bo'shliqlar (probel/tab/qator ko'chirish/NBSP — Python `str.lstrip()`
# standart bo'yicha barchasini bo'sh joy deb hisoblaydi) olib tashlanib tekshiriladi, LEKIN
# katakka yoziladigan qiymat — ASL (o'zgartirilmagan) matn, faqat oldiga `'` qo'shiladi.
def _cell(value: object) -> str:
    text_value = "" if value is None else str(value)
    if text_value.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + text_value
    return text_value


@router.get("/export.csv")
def export_csv(
    ctx: Auditor, db: DB, meta: Meta, filters: Annotated[Filters, Depends()]
) -> Response:
    where, params = filters.sql()
    # R1-4: chegaradan BITTA ortiq qator so'raladi — agar shuncha qaytsa, chegara chindan
    # ham kesib tashlagani (haqiqatda ko'proq qator borligi) ma'lum bo'ladi.
    rows = _rows(db, where, params, EXPORT_LIMIT + 1, 0)
    truncated = len(rows) > EXPORT_LIMIT
    if truncated:
        rows = rows[:EXPORT_LIMIT]
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(["id", "ts", "username", "action", "result", "object_type", "object_id",
                     "request_id", "ip", "details"])
    for r in rows:
        writer.writerow([_cell(v) for v in (
            r.id, r.ts.isoformat(), r.username, r.action, r.result, r.object_type, r.object_id,
            r.request_id, r.ip, json.dumps(r.details, ensure_ascii=False))])
    log_event(meta, AuditAction.AUDIT_EXPORTED, user_id=ctx.user_id,
              details={"filters": filters.as_dict(), "rows": len(rows), "truncated": truncated})
    filename = f"audit_{datetime.now(UTC):%Y%m%d_%H%M}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if truncated:
        headers["X-Export-Truncated"] = "true"
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.post("/verify")
def verify(ctx: Auditor, meta: Meta) -> VerifyOut:
    # R1-2: to'liq jadval bo'yicha HMAC skanerlash arzon amal emas — foydalanuvchi va
    # global chegaralarni SO'ROV BOSHIDA (haqiqiy skanerlashdan oldin) tekshiramiz.
    ratelimit.check("audit_verify_user", str(ctx.user_id), ratelimit.AUDIT_VERIFY_PER_USER)
    ratelimit.check("audit_verify_global", "global", ratelimit.AUDIT_VERIFY_GLOBAL)
    report = verify_chain_snapshot()
    log_event(meta, AuditAction.AUDIT_VERIFIED, user_id=ctx.user_id,
              result="ok" if report.ok else "fail",
              details={"checked": report.checked, "bad_ids": report.bad_ids[:20]})
    return VerifyOut(ok=report.ok, checked=report.checked, bad_ids=report.bad_ids,
                      first_bad_id=report.first_bad_id)
