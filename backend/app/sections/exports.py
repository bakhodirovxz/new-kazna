"""Eksport (TZ 6, TZ 9): .xlsx serverda; brauzerdagi CSV/PNG faqat auditga yoziladi.

Har eksport — `data.exported` (kim, nima, qachon, qaysi filtrlar bilan).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth.context import Ctx, require_perm
from app.auth.permissions import Perm, Section, section_perm
from app.core import ratelimit
from app.core.db import DB
from app.core.errors import ForbiddenError, ValidationFailed
from app.core.request_meta import Meta
from app.sections.deps import PER_PATTERN, SQ, SectionQuery
from app.sections.obzor import build_excel
from app.sections.queries import cash, payments
from app.sections.xlsx import build_workbook

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_LIMIT = ratelimit.Limit(events=10, window=60)
# shortcut: o'zgarmas 30/min; sysconfig kaliti (U1) kerak bo'lsa — admin panelga chiqariladi.
LOG_LIMIT = ratelimit.Limit(events=30, window=60)
# Bo'lim -> sahifalar; ro'yxati yo'q bo'limlar (keyingi rejalar) faqat shakl bo'yicha tekshiriladi.
SECTION_PAGES: dict[str, frozenset[str]] = {
    "obzor": frozenset({"svod", "postup", "rasxod", "excel", "vnimanie"}),
    "kazna": frozenset({"svod", "platezhi", "calendar", "dogovory", "celevye"}),
}

xlsx_router = APIRouter(prefix="/obzor", tags=["export"], dependencies=[
    Depends(require_perm(section_perm(Section.OBZOR), Perm.EXPORT_XLSX.value))])
log_router = APIRouter(prefix="/exports", tags=["export"],
                       dependencies=[Depends(require_perm(Perm.EXPORT_CSV.value))])


class ExportLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["csv", "png"]
    section: Section
    page: Annotated[str, Field(pattern=r"^[a-z]{2,20}$")]
    card: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")]
    br: Annotated[int | None, Field(ge=1)] = None
    per: Annotated[str | None, Field(pattern=PER_PATTERN)] = None
    rows: Annotated[int | None, Field(ge=0, le=1_000_000)] = None


def xlsx_filename(q: SectionQuery) -> str:
    scope = f"br{q.br}" if q.br is not None else "all"
    return f"UGEKAZNA_cashflow_{scope}_{q.per}_{q.today:%Y%m%d}.xlsx"


def _scope_label(db: Session, q: SectionQuery) -> str:
    if q.br is not None:
        name = db.execute(text("SELECT name FROM pub.branches WHERE branch_id = :b"),
                          {"b": q.br}).scalar_one_or_none()
        return str(name or q.br)
    return "все филиалы" if q.branch_ids is None else "доступные филиалы"


@xlsx_router.get("/excel.xlsx", response_class=Response,
                 responses={200: {"content": {XLSX_MEDIA: {}}}})
def excel_xlsx(db: DB, q: SQ, ctx: Ctx, meta: Meta) -> Response:
    ratelimit.check("export_xlsx", str(ctx.user_id), XLSX_LIMIT)
    data = build_excel(db, q)
    body = build_workbook(data, payments.plan_fact(db, q.sel(), q.period()),
                          cash.monthly(db, q.sel(), q.today), _scope_label(db, q))
    log_event(meta, AuditAction.DATA_EXPORTED, user_id=ctx.user_id, object_type="export",
              object_id="obzor.excel",
              details={"format": "xlsx", "section": "obzor", "page": "excel", "br": q.br,
                       "per": q.per, "rows": len(data.detail)})
    return Response(content=body, media_type=XLSX_MEDIA, headers={
        "Content-Disposition": f'attachment; filename="{xlsx_filename(q)}"',
        "Cache-Control": "no-store"})


@log_router.post("/log", status_code=204, response_class=Response)
def export_log(body: ExportLogIn, ctx: Ctx, meta: Meta) -> Response:
    ratelimit.check("export_log", str(ctx.user_id), LOG_LIMIT)
    pages = SECTION_PAGES.get(body.section.value)
    if pages is not None and body.page not in pages:
        raise ValidationFailed(fields=["page"])
    ctx.assert_branch(body.br)
    if section_perm(body.section) not in ctx.permissions:
        raise ForbiddenError()
    log_event(meta, AuditAction.DATA_EXPORTED, user_id=ctx.user_id, object_type="export",
              object_id=f"{body.section.value}.{body.page}",
              details={"format": body.kind, "section": body.section.value, "page": body.page,
                       "card": body.card, "br": body.br, "per": body.per, "rows": body.rows})
    return Response(status_code=204)
